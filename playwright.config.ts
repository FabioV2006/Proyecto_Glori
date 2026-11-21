import { defineConfig } from '@playwright/test'

const port = process.env.GLORI_TEST_PORT || '5000'
const url = 'http://127.0.0.1:' + port

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: url, channel: 'msedge' },
  webServer: {
    command: `"${process.env.GLORI_PYTHON || 'python'}" -B -m flask --app glori run --host 127.0.0.1 --port ${port}`,
    env: { GLORI_DEMO_DATES: '1', GLORI_SHOW_DEMO_ACCOUNTS: '1' },
    url,
    reuseExistingServer: false,
  },
})
