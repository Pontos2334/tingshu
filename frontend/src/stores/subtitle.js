import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const STORAGE_KEY = 'tingshu_subtitle'

function readPersisted() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch { return {} }
}

export const useSubtitleStore = defineStore('subtitle', () => {
  const persisted = readPersisted()

  // Current project
  const currentProjectId = ref(persisted.currentProjectId || null)
  const project = ref(null)
  const segments = ref([])

  // Pipeline state
  const pipelineRunning = ref(false)
  const pipelineStep = ref('')
  const pipelineProgress = ref(0)
  const pipelineMessage = ref('')
  const sseConnected = ref(false)
  const eventSource = ref(null)
  const terminalHandler = ref(null)

  // List filters
  const searchQuery = ref(persisted.searchQuery || '')
  const currentPage = ref(persisted.currentPage || 1)

  function setProject(projectData) {
    project.value = projectData
    currentProjectId.value = projectData?.id || null
    segments.value = projectData?.segments || []
  }

  function updateSegment(segId, data) {
    const idx = segments.value.findIndex(s => s.id === segId)
    if (idx !== -1) {
      segments.value[idx] = { ...segments.value[idx], ...data }
    }
  }

  function setPipelineState(running, step, progress, message) {
    pipelineRunning.value = running
    pipelineStep.value = step || ''
    pipelineProgress.value = progress || 0
    pipelineMessage.value = message || ''
  }

  function normalizeStep(step) {
    const map = {
      extracting: 'extract',
      transcribing: 'transcribe',
      translating: 'translate',
      polishing: 'polish',
    }
    return map[step] || step || ''
  }

  function stepLabel(step) {
    const map = {
      extract: '提取音频',
      transcribe: '语音识别',
      translate: '翻译',
      polish: '润色',
    }
    return map[normalizeStep(step)] || step || ''
  }

  function mergeProjectEvent(event) {
    if (!project.value) return
    const keys = [
      'status', 'current_step', 'error_message', 'error_step', 'error_code', 'error_detail',
      'segment_count', 'translated_count', 'polished_count',
    ]
    for (const key of keys) {
      if (event[key] !== undefined) project.value[key] = event[key]
    }
  }

  function connectSSE(url, onTerminal) {
    disconnectSSE()
    terminalHandler.value = onTerminal || null
    const es = new EventSource(url)
    eventSource.value = es
    sseConnected.value = true

    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        handleSSEEvent(event)
      } catch { /* ignore */ }
    }

    es.onerror = () => {
      sseConnected.value = false
      es.close()
    }
  }

  function handleSSEEvent(event) {
    switch (event.type) {
      case 'snapshot': {
        mergeProjectEvent(event)
        const currentStep = normalizeStep(event.current_step)
        if (currentStep) {
          setPipelineState(true, currentStep, event.progress || 0, `${stepLabel(currentStep)}进行中...`)
          break
        }
        const s = event.status
        if (s === 'failed') {
          const errMsg = event.error_message || project.value?.error_message
          setPipelineState(false, '', 0, errMsg ? `错误: ${errMsg}` : '处理失败')
        } else if (s === 'canceled') {
          setPipelineState(false, '', 0, '已取消')
        } else if (s === 'completed' || s === 'translated' || s === 'polished') {
          setPipelineState(false, '', 100, '处理完成')
        } else if (s === 'uploaded' || s === 'audio_extracted' || s === 'transcribed' || s === 'draft') {
          setPipelineState(false, '', 0, '')
        } else {
          setPipelineState(true, s, 0, '')
        }
        break
      }
      case 'step_started':
        setPipelineState(true, normalizeStep(event.step), 0, event.message || `${stepLabel(event.step)}开始...`)
        break
      case 'progress':
        setPipelineState(true, normalizeStep(event.step), event.progress || 0, event.message || '')
        break
      case 'step_done':
        setPipelineState(true, '', 100, `${stepLabel(event.step)}完成`)
        break
      case 'pipeline_done':
        setPipelineState(false, '', 100, '处理完成')
        mergeProjectEvent(event)
        notifyTerminal(event)
        disconnectSSE()
        break
      case 'pipeline_error':
        setPipelineState(false, '', 0, `错误: ${event.message || event.error}`)
        if (project.value) {
          project.value.status = 'failed'
          project.value.error_message = event.message || event.error
          project.value.error_step = event.step
          project.value.error_code = event.code
          project.value.error_detail = event.detail
        }
        notifyTerminal(event)
        disconnectSSE()
        break
      case 'pipeline_canceled':
        setPipelineState(false, '', 0, '已取消')
        if (project.value) {
          project.value.status = 'canceled'
        }
        notifyTerminal(event)
        disconnectSSE()
        break
    }
  }

  function notifyTerminal(event) {
    const handler = terminalHandler.value
    terminalHandler.value = null
    if (handler) handler(event)
  }

  function disconnectSSE() {
    if (eventSource.value) {
      eventSource.value.close()
      eventSource.value = null
      sseConnected.value = false
    }
    terminalHandler.value = null
  }

  function clearProject() {
    disconnectSSE()
    currentProjectId.value = null
    project.value = null
    segments.value = []
    setPipelineState(false, '', 0, '')
  }

  // Persist filters
  watch([currentProjectId, searchQuery, currentPage], () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      currentProjectId: currentProjectId.value,
      searchQuery: searchQuery.value,
      currentPage: currentPage.value,
    }))
  }, { deep: true })

  return {
    currentProjectId, project, segments,
    pipelineRunning, pipelineStep, pipelineProgress, pipelineMessage,
    sseConnected, searchQuery, currentPage,
    setProject, updateSegment, setPipelineState,
    connectSSE, disconnectSSE, clearProject, handleSSEEvent,
  }
})
