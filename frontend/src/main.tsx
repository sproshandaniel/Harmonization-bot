import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

const originalFetch = window.fetch.bind(window)
window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
  const headers = new Headers(init?.headers)
  const loginEmail = (localStorage.getItem('hb_user_email') || '').trim()
  const fallbackUser = (localStorage.getItem('hb_user') || '').trim()
  const resolvedUser = loginEmail || (fallbackUser.includes('@') ? fallbackUser : '')
  if (resolvedUser && !headers.has('X-HB-User')) {
    headers.set('X-HB-User', resolvedUser)
  }
  return originalFetch(input, { ...(init || {}), headers })
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
