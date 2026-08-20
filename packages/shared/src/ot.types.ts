// Operational Transformation operation types
// Keep in sync with apps/backend/src/documents/ot/operations.py

export type OTOpType = 'insert' | 'delete' | 'retain'

export interface OTOp {
  type: OTOpType
  position: number
  chars?: string   // present for insert
  length?: number  // present for delete / retain
}

export interface OTOperation {
  documentId: string
  revision: number   // revision this op is based on
  ops: OTOp[]
  authorId: string
  clientSeq: number  // client-side sequence number for ack tracking
}
