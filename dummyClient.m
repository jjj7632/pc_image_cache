% August Latta
% This program models the function of the MATLAB GUI using the local PC
% stereo image cache. It responds to SoC image requests by sending cached
% left/right images over TCP using the same binary layout as the Python side.
%
% testSlaveMode, when set, will respond to the board's request for the most
% recent image by putting it into slave mode and then sending a small batch
% of cached frames for processing before resetting back to master mode.

width = 1920;
height = 1080;
testSlaveMode = true;
slaveBatchCount = 5;

% Initialization Parameters
server_ip = '10.0.110.2';
server_port = 9999;
cache_root = fullfile(fileparts(mfilename("fullpath")), "cache");

cache_state = initializeFrameCache(cache_root, width, height);
current_index = numel(cache_state.frames);

client = tcpclient(server_ip, server_port);
fprintf(1, "Connected to server\n");

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% send raw frames from the local stereo cache
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
while true
    cmd = readExactUint8(client, 1);
    switch cmd
        case 10
            if testSlaveMode
                write(client, uint8(98), "uint8");
                disp("98 sent")
            else
                [frame_record, current_index] = getLatestFrame(cache_state, current_index);
                sendFrame(client, frame_record);
                disp("msg 10 processed: sent cached frame " + frame_record.frameNumber + " (" + frame_record.name + ")")
            end

        case 11
            offset = readInt32(client);
            [frame_record, current_index] = getRelativeFrame(cache_state, current_index, -double(offset));
            sendFrame(client, frame_record);
            disp("msg 11 processed: sent cached frame " + frame_record.frameNumber + " (" + frame_record.name + ")")

        case 12
            offset = readInt32(client);
            [frame_record, current_index] = getRelativeFrame(cache_state, current_index, double(offset));
            sendFrame(client, frame_record);
            disp("msg 12 processed: sent cached frame " + frame_record.frameNumber + " (" + frame_record.name + ")")

        case 15
            requested_frame = readInt32(client);
            [frame_record, current_index] = getSpecificFrame(cache_state, requested_frame, current_index);
            sendFrame(client, frame_record);
            disp("msg 15 processed: sent cached frame " + frame_record.frameNumber + " (" + frame_record.name + ")")

        case 21
            frame = readInt32(client);
            X = readFloat32(client);
            Y = readFloat32(client);
            Z = readFloat32(client);
            disp("msg 21 processed: frame #: " + frame + " X: " + X + " Y: " + Y + " Z: " + Z)

        case 22
            in = readExactUint8(client, 1);
            if in == 1
                disp("In")
            else
                disp("Out")
            end

        case 30 % for this test program, 30 terminates the client
            disp("msg 30 received, closing...")
            break

        case 99
            disp("SoC entering slave mode, sending cached frames to process")
            flush(client)
            frames_to_send = min(slaveBatchCount, numel(cache_state.frames));
            current_index = 1;
            for i = 1:frames_to_send
                frame_record = cache_state.frames(current_index);
                sendFrame(client, frame_record);
                current_index = current_index + 1;

                cmd = readExactUint8(client, 1);
                if cmd ~= 21
                    error("Expected CMD_LOG_DATA (21) during slave mode, received %d", cmd);
                end

                frame = readInt32(client);
                X = readFloat32(client);
                Y = readFloat32(client);
                Z = readFloat32(client);
                disp("msg 21 processed: frame #: " + frame + " X: " + X + " Y: " + Y + " Z: " + Z)
            end

            write(client, uint8(1), "uint8"); % reset server

        otherwise
            continue
    end
end
clear client


function cache_state = initializeFrameCache(cache_root, width, height)
    left_dir = fullfile(cache_root, "left_image");
    right_dir = fullfile(cache_root, "right_image");
    
    left_map = buildImageMap(left_dir);
    right_map = buildImageMap(right_dir);
    shared_tokens = intersect(keys(left_map), keys(right_map));
    shared_tokens = sortFrameTokens(shared_tokens);
    
    if isempty(shared_tokens)
        error("No stereo cache frames found in %s and %s", left_dir, right_dir);
    end
    
    frames = repmat(struct("frameNumber", int32(0), "name", "", "leftImage", [], "rightImage", []), 1, numel(shared_tokens));
    for i = 1:numel(shared_tokens)
        token = shared_tokens{i};
        left_image = imread(left_map(token));
        right_image = imread(right_map(token));
    
        frames(i).frameNumber = int32(i);
        frames(i).name = string(token);
        frames(i).leftImage = ensureRgbSize(left_image, width, height);
        frames(i).rightImage = ensureRgbSize(right_image, width, height);
    end
    
    cache_state = struct( ...
        "frames", frames, ...
        "frameCount", numel(frames));
end


function image_map = buildImageMap(folder_path)
    image_map = containers.Map("KeyType", "char", "ValueType", "char");
    
    if ~isfolder(folder_path)
        return;
    end
    
    extensions = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"];
    files = dir(folder_path);
    
    for i = 1:numel(files)
        if files(i).isdir
            continue
        end
    
        [~, name, extension] = fileparts(files(i).name);
        if ~any(strcmpi(extension, extensions))
            continue
        end
    
        token = getFrameToken(name);
        image_map(token) = fullfile(folder_path, files(i).name);
    end
end


function token = getFrameToken(name)
    match = regexp(name, '(\d+)$', 'tokens', 'once');
    if isempty(match)
        token = char(name);
    else
        token = match{1};
    end
end


function sorted_tokens = sortFrameTokens(tokens)
    numeric_tokens = {};
    text_tokens = {};
    
    for i = 1:numel(tokens)
        token = tokens{i};
        if all(isstrprop(token, 'digit'))
            numeric_tokens{end + 1} = token; %#ok<AGROW>
        else
            text_tokens{end + 1} = token; %#ok<AGROW>
        end
    end
    
    if ~isempty(numeric_tokens)
        numeric_values = cellfun(@str2double, numeric_tokens);
        [~, order] = sort(numeric_values);
        numeric_tokens = numeric_tokens(order);
    end
    
    if ~isempty(text_tokens)
        text_tokens = sort(text_tokens);
    end
    
    sorted_tokens = [numeric_tokens, text_tokens];
end


function [frame_record, current_index] = getLatestFrame(cache_state, current_index)
    if nargin < 2 || current_index < 1
        current_index = cache_state.frameCount;
    end
    current_index = cache_state.frameCount;
    frame_record = cache_state.frames(current_index);
end


function [frame_record, current_index] = getRelativeFrame(cache_state, current_index, offset)
    if current_index < 1
        current_index = cache_state.frameCount;
    end
    current_index = max(1, min(cache_state.frameCount, current_index + offset));
    frame_record = cache_state.frames(current_index);
end


function [frame_record, current_index] = getSpecificFrame(cache_state, requested_frame, current_index)
    frame_numbers = arrayfun(@(frame) double(frame.frameNumber), cache_state.frames);
    match_index = find(frame_numbers == double(requested_frame), 1);
    if isempty(match_index)
        [frame_record, current_index] = getLatestFrame(cache_state, current_index);
    else
        current_index = match_index;
        frame_record = cache_state.frames(current_index);
    end
end


function sendFrame(connection, frame_record)
    write(connection, uint8(50), "uint8");
    writeInt32(connection, frame_record.frameNumber);
    write(connection, imageToBytes(frame_record.leftImage), "uint8");
    write(connection, imageToBytes(frame_record.rightImage), "uint8");
end


function bytes = readExactUint8(connection, count)
    bytes = uint8(read(connection, count, "uint8"));
    bytes = bytes(:).';
end


function value = readInt32(connection)
    data = readExactUint8(connection, 4);
    value = typecast(uint8(data), "int32");
    value = swapbytes(value);
end


function value = readFloat32(connection)
    data = readExactUint8(connection, 4);
    value = typecast(uint8(data), "single");
    value = swapbytes(value);
end


function writeInt32(connection, value)
    bytes = typecast(swapbytes(int32(value)), "uint8");
    write(connection, bytes, "uint8");
end


function image = ensureRgbSize(image, width, height)
    image = uint8(image);
    if size(image, 3) == 1
        image = repmat(image, 1, 1, 3);
    end
    if size(image, 1) ~= height || size(image, 2) ~= width
        image = imresize(image, [height, width]);
    end
end


function bytes = imageToBytes(image)
    bytes = uint8(reshape(permute(image, [3, 2, 1]), 1, []));
end
