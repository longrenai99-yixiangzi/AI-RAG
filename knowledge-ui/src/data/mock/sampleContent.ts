import type { KnowledgeNodeSample } from './knowledgeContent'
import { designManagementSamplesByNode } from './designManagementSample'
import { technicalConstructionNodeId, technicalConstructionGraph, technicalConstructionCards, technicalConstructionSources, technicalConstructionCases, technicalConstructionSpace } from './technicalConstructionSample'

export const sampleContentByNode: Record<string, KnowledgeNodeSample> = {
  ...designManagementSamplesByNode,
  [technicalConstructionNodeId]: { graph: technicalConstructionGraph, cards: technicalConstructionCards, sources: technicalConstructionSources, cases: technicalConstructionCases, space: technicalConstructionSpace },
}

export function getKnowledgeNodeSample(nodeId: string) { return sampleContentByNode[nodeId] }
