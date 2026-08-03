import { postJson } from './http'
import type { ContractRequest, ContractResponse } from './contractTypes'

export function simulateContracts(req: ContractRequest): Promise<ContractResponse> {
  return postJson<ContractResponse>('/api/contract/simulate', req)
}
