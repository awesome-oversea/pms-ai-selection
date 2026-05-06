import { readFileSync } from 'node:fs'
import path from 'node:path'

const root = process.cwd().endsWith(`${path.sep}frontend`) ? path.resolve(process.cwd(), '..') : process.cwd()
const files = [
  'frontend/app/page.tsx',
  'frontend/app/layout.tsx',
  'frontend/app/globals.css',
  'frontend/components/common/AppShell.tsx',
  'frontend/middleware.ts',
]

const expectations = [
  ['frontend/app/page.tsx', ['企业级 AI 选品中枢蓝图', '高价值任务状态面', '工作台矩阵']],
  ['frontend/app/layout.tsx', ['AppShell', '企业级 AI 选品中枢']],
  ['frontend/components/common/AppShell.tsx', ['蓝图总览', '选品工作台', '运营台']],
  ['frontend/middleware.ts', ['/knowledge', '/operations']],
]

for (const relative of files) {
  readFileSync(path.join(root, relative), 'utf8')
}

for (const [relative, keywords] of expectations) {
  const content = readFileSync(path.join(root, relative), 'utf8')
  for (const keyword of keywords) {
    if (!content.includes(keyword)) {
      throw new Error(`${relative} 缺少关键字: ${keyword}`)
    }
  }
}

console.log(JSON.stringify({ ok: true, checked: files.length, smoke: 'frontend-blueprint' }))
