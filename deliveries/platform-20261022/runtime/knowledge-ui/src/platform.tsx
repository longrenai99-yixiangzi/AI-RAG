import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { PlatformWorkbench } from './pages/PlatformWorkbench'

createRoot(document.getElementById('root')!).render(<StrictMode><BrowserRouter><PlatformWorkbench /></BrowserRouter></StrictMode>)
