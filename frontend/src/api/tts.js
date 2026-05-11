import api from './index'

export function synthesize(data) {
  return api.post('/tts/synthesize', data)
}

export function synthesizeLong(data) {
  return api.post('/tts/synthesize-long', data, { responseType: 'text', timeout: 600000 })
}

export function preview(data) {
  return api.post('/tts/preview', data, { responseType: 'blob' })
}

// 合成任务 API
export function createSynthesisTask(data) {
  return api.post('/tts/create-task', data)
}

export function getSynthesisTasks(params) {
  return api.get('/tts/tasks', { params })
}

export function getSynthesisTask(taskId) {
  return api.get(`/tts/tasks/${taskId}`)
}

export function resumeSynthesisTask(taskId) {
  return api.post(`/tts/tasks/${taskId}/resume`)
}

export function retryFailedChunks(taskId) {
  return api.post(`/tts/tasks/${taskId}/retry-failed`)
}

export function cancelSynthesisTask(taskId) {
  return api.post(`/tts/tasks/${taskId}/cancel`)
}

export function deleteSynthesisTask(taskId) {
  return api.delete(`/tts/tasks/${taskId}`)
}
