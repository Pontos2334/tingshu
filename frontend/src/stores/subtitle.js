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

  function connectSSE(url) {
    disconnectSSE()
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
      case 'snapshot':
        setPipelineState(true, event.status, 0, '')
        break
      case 'step_started':
        setPipelineState(true, event.step, 0, `${event.step} 开始...`)
        break
      case 'progress':
        setPipelineState(true, event.step, event.progress || 0, event.message || '')
        break
      case 'step_done':
        setPipelineState(true, '', 100, `${event.step} 完成`)
        break
      case 'pipeline_done':
        setPipelineState(false, '', 100, '处理完成')
        if (project.value) {
          project.value.status = event.status || 'completed'
        }
        disconnectSSE()
        break
      case 'pipeline_error':
        setPipelineState(false, '', 0, `错误: ${event.error}`)
        if (project.value) {
          project.value.status = 'failed'
          project.value.error_message = event.error
        }
        disconnectSSE()
        break
      case 'pipeline_canceled':
        setPipelineState(false, '', 0, '已取消')
        if (project.value) {
          project.value.status = 'canceled'
        }
        disconnectSSE()
        break
    }
  }

  function disconnectSSE() {
    if (eventSource.value) {
      eventSource.value.close()
      eventSource.value = null
      sseConnected.value = false
    }
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
    connectSSE, disconnectSSE, clearProject,
  }
})
