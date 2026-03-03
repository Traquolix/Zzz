const { spawn } = require('child_process');

const vitest = spawn('npx', ['vitest', 'run', '--no-coverage', '--reporter=verbose'], {
  stdio: 'inherit',
  timeout: 120000
});

vitest.on('close', (code) => {
  process.exit(code);
});

setTimeout(() => {
  vitest.kill();
  process.exit(124);
}, 120000);
