import api from './index'

export function getRecords(params) {
  return api.get('/audio/records', { params })
}

export function getRecord(id) {
  return api.get(`/audio/records/${id}`)
}

export function deleteRecord(id) {
  return api.delete(`/audio/records/${id}`)
}

export function toggleFavorite(id) {
  return api.put(`/audio/records/${id}/favorite`)
}

export function getFavorites(params) {
  return api.get('/audio/favorites', { params })
}

export function getAudioGroups(params) {
  return api.get('/audio/groups', { params })
}

export function getAudioGroup(groupId) {
  return api.get(`/audio/groups/${groupId}`)
}

export function deleteAudioGroup(groupId) {
  return api.delete(`/audio/groups/${groupId}`)
}

export function getAudioUrl(id) {
  return `/api/audio/file/${id}`
}
