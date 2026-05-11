import api from './index'

export function getPlaylists() {
  return api.get('/playlists')
}

export function createPlaylist(data) {
  return api.post('/playlists', data)
}

export function updatePlaylist(id, data) {
  return api.put(`/playlists/${id}`, data)
}

export function deletePlaylist(id) {
  return api.delete(`/playlists/${id}`)
}

export function addTrack(playlistId, audioId) {
  return api.post(`/playlists/${playlistId}/tracks`, { audio_id: audioId })
}

export function removeTrack(playlistId, trackId) {
  return api.delete(`/playlists/${playlistId}/tracks/${trackId}`)
}

export function getTracks(playlistId) {
  return api.get(`/playlists/${playlistId}/tracks`)
}
