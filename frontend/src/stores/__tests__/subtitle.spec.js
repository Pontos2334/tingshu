import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSubtitleStore } from '../subtitle'

describe('subtitle store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('treats snapshot current_step as running state', () => {
    const store = useSubtitleStore()
    store.setProject({ id: 1, status: 'transcribed', segment_count: 2 })

    store.handleSSEEvent({
      type: 'snapshot',
      status: 'transcribed',
      current_step: 'polishing',
      segment_count: 2,
      polished_count: 0,
    })

    expect(store.pipelineRunning).toBe(true)
    expect(store.pipelineStep).toBe('polish')
    expect(store.project.current_step).toBe('polishing')
  })

  it('keeps detailed pipeline error fields', () => {
    const store = useSubtitleStore()
    store.setProject({ id: 1, status: 'transcribed' })

    store.handleSSEEvent({
      type: 'pipeline_error',
      step: 'translate',
      code: 'llm_http_error',
      message: '翻译接口请求失败',
      detail: 'HTTP 429 rate limit',
    })

    expect(store.pipelineRunning).toBe(false)
    expect(store.pipelineMessage).toContain('翻译接口请求失败')
    expect(store.project.status).toBe('failed')
    expect(store.project.error_code).toBe('llm_http_error')
    expect(store.project.error_detail).toContain('rate limit')
  })

  it('calls terminal callback when the SSE stream finishes', () => {
    const instances = []
    const OriginalEventSource = globalThis.EventSource

    class FakeEventSource {
      constructor(url) {
        this.url = url
        this.close = vi.fn()
        instances.push(this)
      }
    }

    globalThis.EventSource = FakeEventSource
    const store = useSubtitleStore()
    store.setProject({ id: 1, status: 'transcribed' })
    const onTerminal = vi.fn()

    store.connectSSE('/api/subtitle/projects/1/events', onTerminal)
    instances[0].onmessage({
      data: JSON.stringify({
        type: 'pipeline_done',
        status: 'translated',
        segment_count: 2,
        translated_count: 2,
      }),
    })

    expect(onTerminal).toHaveBeenCalledTimes(1)
    expect(instances[0].close).toHaveBeenCalled()
    expect(store.sseConnected).toBe(false)
    expect(store.project.translated_count).toBe(2)

    globalThis.EventSource = OriginalEventSource
  })
})
