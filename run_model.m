function result = run_model(parameters, theta, dataset)
    % create result structure
    result = struct();
    % unpack parameters structure
    A_start = parameters.A;
    
    if nargin > 2
        data = dataset;
    else
        data = parameters.dataset_idx;
    end
    active_layers = parameters.active_layers;
    X = parameters.X;
    n_reps = parameters.n;
    n_data = size(data, 1);
    nt = parameters.T;
    dt = parameters.dt;

    % Initialize the accumulators
    A_av = zeros(size(A_start));
    simulation_times = zeros(1, n_data);
    % U = parameters.U;
    exitflag_1 = 0;
    exitflag_2 = 0;
    percentage_model = zeros(nt, 1);
    percentage_squared_error = 0;

    % dataset-derived indices are constant across repetitions
    x_ind = parameters.dataset_idx(:,1);
    y_ind = parameters.dataset_idx(:,2);
    point_count = size(parameters.dataset_idx, 1);
    time_axis = (1:nt)';
    data_hits = parameters.dataset_idx(:,3) <= time_axis';
    percentage_data_const = sum(data_hits, 1)' ./ point_count;

    % check if parameters specifies to calculate W
    if isfield(parameters, 'calculate_W')
        calculate_W = parameters.calculate_W;
        W = zeros(length(theta), n_data);
    else
        calculate_W = false;
        W = 0;
    end

    stream = create_random_stream(parameters);
    data_times = data(:,3);

    for rep = 1:n_reps
        U = rand(stream, size(A_start)).*parameters.W;
        % Run the model for each instance
        if calculate_W == false
            [A, exfl1] = run_model_av(A_start, nt, theta, X, U, active_layers);
            % calculate arrival times
            [times, exfl2] = calculate_times(A, data);
            
        elseif calculate_W
            f = @(theta)calculate_times(run_model_av(A_start, nt, theta, X, U, active_layers),data)*dt;
            g = calculateGradient(f, theta, 0.001, 1);
            W = W + g;
            [A, exfl1] = run_model_av(A_start, nt, theta, X, U, active_layers);
            % calculate arrival times
            [times, exfl2] = calculate_times(A, data);
        end
        A_av = A_av + double(A);  % Convert to double to accumulate          
        simulation_times = simulation_times + double(times)';

        exitflag_1 = exitflag_1 + exfl1;
        exitflag_2 = exitflag_2 + exfl2;
        
        per_model = get_model_percentage(A, x_ind, y_ind);
        percentage_model = percentage_model + per_model;
        percentage_squared_error = percentage_squared_error + sum((percentage_data_const-per_model).^2);
        
        
    end


    % Finalize the average
    simulation_times = simulation_times / n_reps ;
    A_av = A_av / n_reps;

    % assign values to result structure
    result.A = A_av;
    result.times = simulation_times;
    result.errors = calculate_error(data, simulation_times, dt, "full");
    result.squared_error = sum((data_times - simulation_times').^2) * parameters.dt.^2 / n_data;
    result.percentage_squared_error = percentage_squared_error / n_reps / n_data;
    result.percentage_data = percentage_data_const;
    result.percentage_model = percentage_model / n_reps;
    result.exitflag_1 = exitflag_1 / n_reps;
    result.exitflag_2 = exitflag_2 / n_reps;

    if calculate_W
        W = W ./ n_reps;
        W = W*W';
        result.W = W / n_data;
    end
end

function stream = create_random_stream(parameters)
    if isfield(parameters, 'random')
        random_setting = parameters.random;
    else
        random_setting = 12;
    end

    if (isstring(random_setting) && isscalar(random_setting)) || ischar(random_setting)
        if strcmpi(char(random_setting), 'shuffle')
            stream = RandStream('Threefry', 'Seed', shuffled_seed());
            return;
        end
        error('run_model:InvalidRandomSetting', ...
            'parameters.random must be numeric or ''shuffle''.');
    end

    validateattributes(random_setting, {'numeric'}, ...
        {'scalar', 'integer', 'finite', 'nonnegative'}, mfilename, 'parameters.random');
    stream = RandStream('Threefry', 'Seed', double(random_setting));
end

function seed = shuffled_seed()
    worker = getCurrentTask();
    worker_offset = 0;
    if ~isempty(worker)
        worker_offset = worker.ID;
    end

    timestamp = posixtime(datetime('now', 'TimeZone', 'UTC'));
    seed = mod(floor(timestamp * 1e6) + worker_offset, 2^32 - 1);
end


function [A, exitflag] = run_model_av(A_start, nt, theta, X, U, active_layers)
    A = A_start;
    flag = 0;
    for t = 2:nt
        [extflg1, A(:,:,t)] = step(A(:,:,t-1)+A_start(:,:,t-1), theta, X, U(:,:,t), active_layers);
        flag = flag + extflg1/nt;
    end
    if nargout > 1
        exitflag = flag;
    end
end


function [exfl1,a] = step(a, theta, X, U, active_layers)
    [Fn,Fs,Fw,Fe] = frontier(a); % find adjacent cells to currently activated ones
    F = Fn | Fs | Fw | Fe;

    theta_ind = 1;
    X_ind = 1;
    M = zeros(size(F));
    if active_layers(1)
        M = M + theta(theta_ind);
        theta_ind = theta_ind + 1;
    end
    if active_layers(2)
        ew_mask = double(Fe | Fw);
        ns_mask = double(Fn | Fs);
        M = M + theta(theta_ind) * (ew_mask - ns_mask);
        theta_ind = theta_ind + 1;
    end
    for layer = active_layers(3:end)
        if layer
            M = M + theta(theta_ind)*X{X_ind};
            theta_ind = theta_ind + 1;
            X_ind = X_ind + 1;
        end
    end

    M = F .* M;

    f = find(F); % indices of frontier cells
    if isempty(f)
        exfl1 = 0.5;
        return;
    end
    probabilities = 1./(1 + exp(-M(f)));
    adopt = U(f) <= probabilities;
    a(f(adopt)) = true; % update activated cells to include adopted
    exfl1 = mean(M(f));

end


function [fN, fS, fW, fE] = frontier(A)
    % FRONTIER finds all adjacent cells in a two-dimensional array A to
    % true cells.

    [m,n] = size(A);

    % North
    fN = [diff(A) > 0; false(1,n)];

    % South
    fS = [false(1,n); flipud(diff(flipud(A)) > 0)];

    % West
    fW = [(diff(A') > 0)', false(m,1)];

    % East
    fE = [false(m,1), (flipud(diff(flipud(A')) > 0))'];

    end

function model_percentage = get_model_percentage(A, x_ind, y_ind)
    [~,~,nt] = size(A);
    model_percentage = zeros(nt,1);
    points = numel(x_ind);
    for i = 1:nt
        values = A(sub2ind(size(A), x_ind, y_ind, i*ones(points,1)));
        model_percentage(i) = sum(values) / points;
    end
end
