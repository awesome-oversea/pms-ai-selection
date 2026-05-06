import { defineConfig } from '@playwright/test'

const browserChannel = process.env.PLAYWRIGHT_BROWSER_CHANNEL ?? 'msedge'
const recordVideo = process.env.PLAYWRIGHT_RECORD_VIDEO === '1' && process.env.PLAYWRIGHT_FFMPEG_READY === '1'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  expect: {
    timeout: 5000,
  },
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],
  outputDir: 'test-results',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:3100',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    ...(recordVideo ? { video: 'on' as const } : {}),
    ...(browserChannel ? { channel: browserChannel } : {}),
  },
  webServer: [
    {
      command: 'powershell -NoProfile -Command "$env:APP_HOST_PORT=\'18000\'; $env:SEC_SECRET_KEY=\'playwright-local-superuser-secret-key-32chars\'; $env:SEC_LOCAL_BOOTSTRAP_SUPERUSER_ENABLED=\'true\'; $env:SEC_LOCAL_BOOTSTRAP_SUPERUSER_USERNAME=\'admin-e2e\'; $env:SEC_LOCAL_BOOTSTRAP_SUPERUSER_PASSWORD=\'Admin123!\'; $env:SEC_LOCAL_BOOTSTRAP_SUPERUSER_EMAIL=\'admin-e2e@example.com\'; $env:REPORT_CENTER_STATE_PATH=\'artifacts/report_center/playwright-state.json\'; Set-Location ..; python -m uvicorn src.main:app --host 127.0.0.1 --port 18000"',
      url: 'http://127.0.0.1:18000/health',
      reuseExistingServer: true,
      timeout: 120000,
    },
    {
      command: 'powershell -NoProfile -Command "$env:NEXT_PUBLIC_API_BASE=\'http://127.0.0.1:18000/api/v1\'; npm run dev -- --hostname 127.0.0.1 --port 3100"',
      url: 'http://127.0.0.1:3100',
      reuseExistingServer: true,
      timeout: 120000,
    },
  ],
})
