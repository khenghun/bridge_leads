import { postJson } from './http'
import type {
  AnalyzeRequest, AnalyzeResponse, PositionRequest, PositionResponse,
} from './playTypes'

/** Grade every decision one seat made across the whole recorded play. */
export function analyzePlay(req: AnalyzeRequest): Promise<AnalyzeResponse> {
  return postJson<AnalyzeResponse>('/api/play/analyze', req)
}

/** Grade the legal cards for whoever is on play at one position. */
export function gradePosition(req: PositionRequest): Promise<PositionResponse> {
  return postJson<PositionResponse>('/api/play/position', req)
}
