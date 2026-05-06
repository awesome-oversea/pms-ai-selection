export default function App() {
  return (
    <main style={{ fontFamily: 'Arial, sans-serif', padding: 24 }}>
      <h1>PMS 正式选品工作台</h1>
      <p>这是独立前端工程骨架，当前后端运行入口为 /workbench/selection。</p>
      <ul>
        <li>前端工程：frontend/</li>
        <li>BFF 汇总接口：/api/v1/bff/workbench/selection/summary</li>
        <li>BFF 任务接口：/api/v1/bff/workbench/selection/tasks</li>
      </ul>
    </main>
  )
}
