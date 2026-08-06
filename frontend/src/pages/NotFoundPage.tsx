import { Button, EmptyState } from '../components'

interface NotFoundPageProps {
  onNavigate: (path: string) => void
}

export function NotFoundPage({ onNavigate }: NotFoundPageProps) {
  return (
    <EmptyState
      title="페이지를 찾을 수 없습니다"
      description="주소가 바뀌었거나 아직 제공되지 않는 메뉴입니다."
      action={<Button onClick={() => onNavigate('/dashboard')}>대시보드로 돌아가기</Button>}
      symbol="404"
    />
  )
}
