import api from './index'

export function generateContent(data) {
  return api.post('/ai/generate', data)
}

export function getTemplates() {
  return api.get('/ai/templates')
}

export function getTemplate(id) {
  return api.get(`/ai/templates/${id}`)
}

export function createTemplate(data) {
  return api.post('/ai/templates', data)
}

export function updateTemplate(id, data) {
  return api.put(`/ai/templates/${id}`, data)
}

export function deleteTemplate(id) {
  return api.delete(`/ai/templates/${id}`)
}

export function getGenerationHistory(params) {
  return api.get('/ai/history', { params })
}

export function deleteGeneration(id) {
  return api.delete(`/ai/history/${id}`)
}
