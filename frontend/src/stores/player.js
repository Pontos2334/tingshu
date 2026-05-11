import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getAudioUrl } from '../api/audio'

export const usePlayerStore = defineStore('player', () => {
  const audio = ref(null)
  const currentId = ref(null)
  const currentTitle = ref('')
  const currentSourceType = ref('')
  const currentSourceUrl = ref('')
  const isPlaying = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const playbackRate = ref(1)
  const queue = ref([])
  const queueContext = ref(null)
  const objectUrl = ref('')

  const hasSource = computed(() => Boolean(currentSourceUrl.value))

  function normalizeTrack(track, meta = {}) {
    if (typeof track === 'number') {
      return {
        id: track,
        title: meta.title || '',
        sourceType: meta.sourceType || 'record',
      }
    }

    return {
      id: track.id,
      title: meta.title || track.title || '',
      sourceType: meta.sourceType || track.sourceType || 'record',
    }
  }

  function revokeObjectUrl() {
    if (objectUrl.value) {
      URL.revokeObjectURL(objectUrl.value)
      objectUrl.value = ''
    }
  }

  function setAudio(el) {
    audio.value = el
    el.playbackRate = playbackRate.value
    el.addEventListener('timeupdate', () => {
      currentTime.value = el.currentTime
    })
    el.addEventListener('loadedmetadata', () => {
      duration.value = el.duration
    })
    el.addEventListener('play', () => {
      isPlaying.value = true
    })
    el.addEventListener('pause', () => {
      isPlaying.value = false
    })
    el.addEventListener('ended', playNext)
  }

  function play(trackOrId, meta = {}) {
    if (!audio.value) return
    revokeObjectUrl()
    const track = normalizeTrack(trackOrId, meta)
    currentId.value = track.id
    currentTitle.value = track.title
    currentSourceType.value = track.sourceType
    currentSourceUrl.value = getAudioUrl(track.id)
    audio.value.src = currentSourceUrl.value
    audio.value.play()
  }

  function pause() {
    if (audio.value) {
      audio.value.pause()
    }
  }

  function resume() {
    if (audio.value) {
      audio.value.play()
    }
  }

  function stop() {
    if (audio.value) {
      audio.value.pause()
      audio.value.currentTime = 0
    }
  }

  function seek(time) {
    if (audio.value) {
      audio.value.currentTime = time
    }
  }

  function setRate(rate) {
    playbackRate.value = rate
    if (audio.value) {
      audio.value.playbackRate = rate
    }
  }

  function playBlob(blob, meta = {}) {
    if (!audio.value) return
    revokeObjectUrl()
    const url = URL.createObjectURL(blob)
    objectUrl.value = url
    currentId.value = null
    currentTitle.value = meta.title || '临时音频'
    currentSourceType.value = meta.sourceType || 'preview'
    currentSourceUrl.value = url
    audio.value.src = url
    audio.value.play()
  }

  function playUrl(url, meta = {}) {
    if (!audio.value) return
    revokeObjectUrl()
    currentId.value = null
    currentTitle.value = meta.title || '外部音频'
    currentSourceType.value = meta.sourceType || 'external'
    currentSourceUrl.value = url
    audio.value.src = url
    audio.value.play()
  }

  function setQueue(items, context = null) {
    queue.value = items.map(item => normalizeTrack(item))
    queueContext.value = context
  }

  function playNext() {
    const idx = queue.value.findIndex(item => item.id === currentId.value)
    if (idx >= 0 && idx < queue.value.length - 1) {
      play(queue.value[idx + 1])
    } else {
      isPlaying.value = false
    }
  }

  function playPrev() {
    const idx = queue.value.findIndex(item => item.id === currentId.value)
    if (idx > 0) {
      play(queue.value[idx - 1])
    }
  }

  return {
    currentId, currentTitle, currentSourceType, currentSourceUrl, isPlaying, currentTime, duration, playbackRate, queue, queueContext, hasSource,
    setAudio, play, playBlob, playUrl, pause, resume, stop, seek, setRate, setQueue, playNext, playPrev,
  }
})
