import { useEffect, useState } from 'react'
import { domains, getChildren } from '../../data/mock/knowledgeTree'
import type { KnowledgeNode } from '../../types/knowledge'

type Props = { selectedId: string; onSelect: (node: KnowledgeNode) => void }

export function KnowledgeTree({ selectedId, onSelect }: Props) {
  const [expandedCategoryId, setExpandedCategoryId] = useState<string>()
  useEffect(() => {
    const category = domains.flatMap((domain) => getChildren(domain.id)).find((item) => getChildren(item.id).some((leaf) => leaf.id === selectedId))
    if (category) setExpandedCategoryId(category.id)
  }, [selectedId])
  return <div className="knowledge-tree">
    {domains.map((domain) => <div className="tree-domain" key={domain.id}>
      <button className={selectedId === domain.id ? 'selected' : ''} onClick={() => onSelect(domain)}><b>{domain.name}</b><span>{domain.childrenCount}</span></button>
      {getChildren(domain.id).map((category) => <div key={category.id} className="tree-category">
        <button className={`tree-child ${selectedId === category.id ? 'selected' : ''}`} onClick={() => { onSelect(category); setExpandedCategoryId(expandedCategoryId === category.id ? undefined : category.id) }}><span>{category.name}</span><small>{category.knowledgeCount}</small></button>
        {expandedCategoryId === category.id && getChildren(category.id).map((leaf) => <button className={`tree-leaf ${selectedId === leaf.id ? 'selected' : ''}`} key={leaf.id} onClick={() => onSelect(leaf)}><span>{leaf.name}</span><small>{leaf.knowledgeCount}</small></button>)}
      </div>)}
    </div>)}
  </div>
}
