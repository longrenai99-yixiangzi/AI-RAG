import { Link } from 'react-router-dom'

export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return <section className="placeholder-page"><span className="eyebrow">V0.1 PLACEHOLDER</span><h1>{title}</h1><p>{description}</p><Link className="primary-link" to="/framework">进入知识框架</Link></section>
}
