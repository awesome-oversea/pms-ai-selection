import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const root = process.cwd().endsWith(`${path.sep}frontend`) ? path.resolve(process.cwd(), '..') : process.cwd()
const artifactsDir = path.join(root, 'artifacts', 'frontend')
const playwrightReportDir = path.join(root, 'frontend', 'playwright-report')
const playwrightResultsDir = path.join(root, 'frontend', 'test-results')

mkdirSync(artifactsDir, { recursive: true })

function collectFiles(baseDir, predicate = () => true) {
  if (!existsSync(baseDir)) return []
  const entries = []
  for (const name of readdirSync(baseDir)) {
    const absolute = path.join(baseDir, name)
    const stat = statSync(absolute)
    if (stat.isDirectory()) {
      entries.push(...collectFiles(absolute, predicate))
      continue
    }
    if (!predicate(name, absolute)) continue
    entries.push({
      name,
      path: path.relative(root, absolute).replaceAll('\\', '/'),
      size_bytes: stat.size,
      updated_at: stat.mtime.toISOString(),
    })
  }
  return entries
}

const screenshots = collectFiles(artifactsDir, (name) => name.endsWith('.png'))
const videos = collectFiles(playwrightResultsDir, (name) => name.endsWith('.webm'))
const traces = collectFiles(playwrightResultsDir, (name) => name.endsWith('.zip'))
const reportFiles = collectFiles(playwrightReportDir)

const manifest = {
  generated_at: new Date().toISOString(),
  summary: {
    screenshot_total: screenshots.length,
    video_total: videos.length,
    trace_total: traces.length,
    report_file_total: reportFiles.length,
  },
  screenshots,
  videos,
  traces,
  report_files: reportFiles,
}

const output = path.join(artifactsDir, 'evidence_manifest.json')
writeFileSync(output, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8')

console.log(JSON.stringify({ ok: true, output: path.relative(root, output).replaceAll('\\', '/'), summary: manifest.summary }))
