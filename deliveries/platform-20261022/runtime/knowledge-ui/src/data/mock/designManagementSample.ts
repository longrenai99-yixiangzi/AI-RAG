import type { KnowledgeNode } from '../../types/knowledge'
import type { KnowledgeNodeSample } from './knowledgeContent'
// Public delivery excludes private catalog and business content.
export const designManagementCategorySeeds: Array<[string, string, string[]]> = []
export const designManagementGraphNodes: KnowledgeNode[] = []
export const designManagementSamplesByNode: Record<string, KnowledgeNodeSample> = {}
