import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'
import { useWorkflowStore } from '../workflow'

describe('workflow store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('restores persisted workflow state', () => {
    localStorage.setItem('tingshu_workflow', JSON.stringify({
      draftText: '已保存草稿',
      selectedVoice: '冰糖',
      selectedVoiceId: null,
      styles: ['温柔'],
      chunkSize: 700,
      currentTaskId: 'task-1',
      taskSnapshot: { task_id: 'task-1', status: 'running', chunks: [] },
      recentOutputs: [{ id: 1, topic: '历史故事', text: '内容', model: 'deepseek-chat', createdAt: '2026-05-11 10:00:00' }],
    }))

    const store = useWorkflowStore()

    expect(store.draftText).toBe('已保存草稿')
    expect(store.selectedVoice).toBe('冰糖')
    expect(store.styles).toEqual(['温柔'])
    expect(store.chunkSize).toBe(700)
    expect(store.currentTaskId).toBe('task-1')
    expect(store.taskSnapshot.status).toBe('running')
    expect(store.recentOutputs).toHaveLength(1)
  })

  it('persists task state and caps recent outputs', async () => {
    const store = useWorkflowStore()

    store.setTaskState('task-99', { task_id: 'task-99', status: 'pending', chunks: [] })
    for (let index = 0; index < 10; index += 1) {
      store.addRecentOutput({
        id: index,
        topic: `topic-${index}`,
        text: `text-${index}`,
        model: 'deepseek-chat',
        createdAt: `2026-05-11 ${index}`,
      })
    }
    await nextTick()
    await new Promise(resolve => setTimeout(resolve, 350))

    const persisted = JSON.parse(localStorage.getItem('tingshu_workflow'))
    expect(persisted.currentTaskId).toBe('task-99')
    expect(persisted.taskSnapshot.status).toBe('pending')
    expect(store.recentOutputs).toHaveLength(8)

    store.clearTaskState()
    await nextTick()
    expect(store.currentTaskId).toBe('')
    expect(store.taskSnapshot).toBeNull()
  })
})
