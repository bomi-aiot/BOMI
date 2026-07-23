import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { BomiProvider } from './state/BomiContext'
import './styles.css'

const rootElement = document.getElementById('root')

if (!rootElement) {
  throw new Error('BOMI 앱을 마운트할 #root 요소를 찾지 못했습니다.')
}

createRoot(rootElement).render(
  <StrictMode>
    <BomiProvider>
      <App />
    </BomiProvider>
  </StrictMode>,
)
