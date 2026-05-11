import api from './index'

export function getPresets() {
  return api.get('/voices/presets')
}

export function getCustomVoices() {
  return api.get('/voices/custom')
}

export function designVoice(data) {
  return api.post('/voices/design', data)
}

export function cloneVoice(formData) {
  return api.post('/voices/clone', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function getVoicePreviewUrl(id) {
  return `/api/voices/preview/${id}`
}

export function deleteVoice(id) {
  return api.delete(`/voices/custom/${id}`)
}
