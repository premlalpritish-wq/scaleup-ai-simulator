const INPUT_NAMES = new Set([
  'initial_biomass_concentration', 'initial_glycerol_concentration',
  'initial_complex_substrate_concentration', 'initial_dissolved_oxygen',
  'initial_culture_volume', 'feed_glycerol_concentration',
  'feed_complex_substrate_concentration', 'feed_flow_rate', 'feed_start_time',
]);

export function validateWorkerRequest(request) {
  if (!request || typeof request !== 'object' || Array.isArray(request)) throw new Error('Request must be a JSON object.');
  if (request.op === 'manifest') {
    if (Object.keys(request).some((key) => key !== 'op')) throw new Error('The manifest operation accepts no additional fields.');
    return;
  }
  if (request.op !== 'run') throw new Error('Only the fixed Ganjave manifest and run operations are available.');
  if (Object.keys(request).some((key) => !['op', 'inputs', 'parameters'].includes(key))) throw new Error('The run request contains an unsupported field.');
  const { inputs, parameters } = request;
  if (!inputs || typeof inputs !== 'object' || Array.isArray(inputs)) throw new Error('Model inputs must be a JSON object.');
  for (const [name, item] of Object.entries(inputs)) {
    if (!INPUT_NAMES.has(name) || !item || typeof item !== 'object' || Array.isArray(item) || !Number.isFinite(item.value)) {
      throw new Error(`Unsupported or malformed Ganjave input: ${name}.`);
    }
  }
  if (!parameters || typeof parameters !== 'object' || Array.isArray(parameters)) throw new Error('Simulation parameters must be a JSON object.');
  if (!['batch', 'fed_batch'].includes(parameters.mode || 'batch')) throw new Error('The Ganjave operating mode must be batch or fed_batch.');
  if (!Number.isFinite(parameters.duration_h) || parameters.duration_h <= 0 || parameters.duration_h > 48) {
    throw new Error('Run duration must be finite, greater than zero, and no more than 48 hours.');
  }
  const times = parameters.output_times_h || [];
  if (!Array.isArray(times) || times.length > 5001 || times.some((time) => !Number.isFinite(time))) {
    throw new Error('At most 5,001 finite output times are allowed.');
  }
  const solver = parameters.solver || {};
  const maxSteps = solver.max_steps ?? 200000;
  const maxRejections = solver.max_range_rejections ?? 60;
  if (!Number.isInteger(maxSteps) || maxSteps < 1 || maxSteps > 200000) throw new Error('The solver step budget must be between 1 and 200,000.');
  if (!Number.isInteger(maxRejections) || maxRejections < 1 || maxRejections > 60) throw new Error('The solver range-rejection budget must be between 1 and 60.');
}
