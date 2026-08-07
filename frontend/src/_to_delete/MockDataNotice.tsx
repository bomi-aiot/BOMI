export interface MockDataNoticeProps {
  message?: string;
  apiBaseUrl?: string;
}

export function MockDataNotice({
  message = '현재 화면은 예시 데이터로 동작합니다. 실제 API 연동 전 표시 내용이 달라질 수 있습니다.',
  apiBaseUrl,
}: MockDataNoticeProps) {
  return (
    <aside className="mock-data-notice" aria-label="개발 데이터 안내">
      <span className="mock-data-notice__label">개발용</span>
      <p className="mock-data-notice__message">{message}</p>
      {apiBaseUrl ? (
        <code className="mock-data-notice__api">{apiBaseUrl}</code>
      ) : null}
    </aside>
  );
}
