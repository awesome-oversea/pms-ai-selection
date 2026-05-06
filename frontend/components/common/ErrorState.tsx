export default function ErrorState({ message }: { message: string }) {
  return <div className="card" style={{ borderLeft: '4px solid #dc2626' }}><strong>加载失败：</strong>{message}</div>
}
