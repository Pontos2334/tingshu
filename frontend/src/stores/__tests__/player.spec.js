import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePlayerStore } from '../player'

vi.mock('../../api/audio', () => ({
  getAudioUrl: (id) => `/api/audio/file/${id}`,
}))

function createAudioStub(playImpl = () => Promise.resolve()) {
  return {
    src: '',
    currentTime: 0,
    duration: 0,
    playbackRate: 1,
    play: vi.fn(playImpl),
    pause: vi.fn(),
    addEventListener: vi.fn(),
  }
}

describe('player store', () => {
  let visibilityDescriptor
  let createObjectURLDescriptor
  let revokeObjectURLDescriptor

  beforeEach(() => {
    setActivePinia(createPinia())
    visibilityDescriptor = Object.getOwnPropertyDescriptor(document, 'visibilityState')
    createObjectURLDescriptor = Object.getOwnPropertyDescriptor(URL, 'createObjectURL')
    revokeObjectURLDescriptor = Object.getOwnPropertyDescriptor(URL, 'revokeObjectURL')
  })

  afterEach(() => {
    if (visibilityDescriptor) {
      Object.defineProperty(document, 'visibilityState', visibilityDescriptor)
    }
    if (createObjectURLDescriptor) {
      Object.defineProperty(URL, 'createObjectURL', createObjectURLDescriptor)
    } else {
      delete URL.createObjectURL
    }
    if (revokeObjectURLDescriptor) {
      Object.defineProperty(URL, 'revokeObjectURL', revokeObjectURLDescriptor)
    } else {
      delete URL.revokeObjectURL
    }
  })

  it('does not autoplay queued results while document is hidden', async () => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    })

    const player = usePlayerStore()
    const audio = createAudioStub()
    player.setAudio(audio)

    const started = await player.playWhenVisible({
      id: 42,
      title: '长文本结果',
      sourceType: 'record',
    })

    expect(started).toBe(false)
    expect(audio.play).not.toHaveBeenCalled()
    expect(player.currentId).toBe(42)
    expect(player.currentTitle).toBe('长文本结果')
    expect(player.currentSourceUrl).toBe('/api/audio/file/42')
  })

  it('keeps preview source ready without playing when document is hidden', async () => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'hidden',
    })

    const player = usePlayerStore()
    const audio = createAudioStub()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(() => 'blob:preview'),
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    })
    player.setAudio(audio)

    const started = await player.playBlob(new Blob(['preview']), {
      title: '试听',
      sourceType: 'preview',
      requireVisible: true,
    })

    expect(started).toBe(false)
    expect(audio.play).not.toHaveBeenCalled()
    expect(player.currentTitle).toBe('试听')
    expect(player.currentSourceUrl).toBe('blob:preview')
  })

  it('swallows playback promise rejections from the browser', async () => {
    const player = usePlayerStore()
    const audio = createAudioStub(() => Promise.reject(new Error('autoplay blocked')))
    player.setAudio(audio)

    await expect(player.playUrl('/preview.wav', { title: '试听' })).resolves.toBe(false)
    expect(audio.play).toHaveBeenCalledTimes(1)
    expect(player.isPlaying).toBe(false)
  })
})
