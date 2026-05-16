import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'tingshu_workflow'

function debounce(fn, ms) {
  let timer = null
  return (...args) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), ms)
  }
}

function readPersistedState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export const useWorkflowStore = defineStore('workflow', () => {
  const persisted = readPersistedState()

  const draftText = ref(persisted.draftText || '')
  const selectedVoice = ref(persisted.selectedVoice || '')
  const selectedVoiceId = ref(persisted.selectedVoiceId || null)
  const styles = ref(Array.isArray(persisted.styles) ? persisted.styles : [])
  const chunkSize = ref(persisted.chunkSize || 500)
  const currentTaskId = ref(persisted.currentTaskId || '')
  const taskSnapshot = ref(persisted.taskSnapshot || null)
  const recentOutputs = ref(Array.isArray(persisted.recentOutputs) ? persisted.recentOutputs : [])

  // SSE 连接状态（不持久化）
  const sseConnected = ref(false)
  const sseReconnecting = ref(false)

  const persistState = debounce(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        draftText: draftText.value,
        selectedVoice: selectedVoice.value,
        selectedVoiceId: selectedVoiceId.value,
        styles: styles.value,
        chunkSize: chunkSize.value,
        currentTaskId: currentTaskId.value,
        taskSnapshot: taskSnapshot.value,
        recentOutputs: recentOutputs.value,
      }))
    } catch { /* quota exceeded */ }
  }, 300)

  watch(
    [draftText, selectedVoice, selectedVoiceId, styles, chunkSize, currentTaskId, taskSnapshot, recentOutputs],
    persistState,
    { deep: true }
  )

  function setDraftText(text) {
    draftText.value = text
  }

  function setVoiceSelection(voice, voiceId = null) {
    selectedVoice.value = voice
    selectedVoiceId.value = voiceId
  }

  function setStyles(nextStyles) {
    styles.value = [...nextStyles]
  }

  function setChunkSize(size) {
    chunkSize.value = size
  }

  function setTaskState(taskId, snapshot = null) {
    currentTaskId.value = taskId || ''
    taskSnapshot.value = snapshot
  }

  function clearTaskState() {
    currentTaskId.value = ''
    taskSnapshot.value = null
  }

  function updateTaskSnapshot(snapshot) {
    taskSnapshot.value = snapshot
  }

  function addRecentOutput(output) {
    recentOutputs.value = [output, ...recentOutputs.value.filter(item => item.id !== output.id)].slice(0, 8)
  }

  function setSseState(connected, reconnecting = false) {
    sseConnected.value = connected
    sseReconnecting.value = reconnecting
  }

  return {
    draftText,
    selectedVoice,
    selectedVoiceId,
    styles,
    chunkSize,
    currentTaskId,
    taskSnapshot,
    recentOutputs,
    sseConnected,
    sseReconnecting,
    setDraftText,
    setVoiceSelection,
    setStyles,
    setChunkSize,
    setTaskState,
    clearTaskState,
    updateTaskSnapshot,
    addRecentOutput,
    setSseState,
  }
})
