import api from './index'

// Projects
export const createSubtitleProject = (data) => api.post('/subtitle/projects', data)
export const getSubtitleProjects = (params) => api.get('/subtitle/projects', { params })
export const getSubtitleProject = (id) => api.get(`/subtitle/projects/${id}`)
export const updateSubtitleProject = (id, data) => api.put(`/subtitle/projects/${id}`, data)
export const deleteSubtitleProject = (id) => api.delete(`/subtitle/projects/${id}`)

// Video upload
export const uploadSubtitleVideo = (id, formData, onProgress) =>
  api.post(`/subtitle/projects/${id}/video`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000,
    onUploadProgress: onProgress,
  })

// Import SRT
export const importSubtitleSrt = (id, formData) =>
  api.post(`/subtitle/projects/${id}/import-srt`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

// Pipeline
export const startSubtitleProcess = (id, data) => api.post(`/subtitle/projects/${id}/process`, data)
export const cancelSubtitleProcess = (id) => api.post(`/subtitle/projects/${id}/cancel`)

// Segments
export const getSubtitleSegments = (id) => api.get(`/subtitle/projects/${id}/segments`)
export const updateSubtitleSegment = (id, segId, data) => api.put(`/subtitle/projects/${id}/segments/${segId}`, data)

// Export
export const exportSubtitles = (id, data) => api.post(`/subtitle/projects/${id}/export`, data)
export const getSubtitleOutputs = (id) => api.get(`/subtitle/projects/${id}/outputs`)
export const downloadSubtitleOutput = (id, outputId) =>
  api.get(`/subtitle/projects/${id}/outputs/${outputId}/download`, { responseType: 'blob' })

// SSE URL helper
export function getSubtitleEventsUrl(id) {
  const base = api.defaults.baseURL || ''
  return `${base}/subtitle/projects/${id}/events`
}
