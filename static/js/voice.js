const qs = (sel) => document.querySelector(sel)
const messagesEl = qs('#messages')
const transcriptLog = qs('#transcript-log')
const audioPlayer = qs('#audio-player')
const audioProgress = qs('#audio-progress')
const audioStatus = qs('#audio-status')
const micBtn = qs('#mic-btn')
const sendBtn = qs('#send-btn')
const textInput = qs('#text-input')
const copyLast = qs('#copy-last')
const healthBtn = qs('#health-check')
const resetBtn = qs('#reset-history')
const waveform = qs('#waveform')
const themeToggle = qs('#theme-toggle')

const state = {
  history: [],
  isRecording: false,
  // Custom WAV recorder state (avoids ffmpeg on server)
  stream: null,
  sourceNode: null,
  processorNode: null,
  wavBuffers: [],
  sampleRate: 0,
  samplesCollected: 0,
  startedAt: 0,
  audioContext: null,
  analyser: null,
  silenceTimeout: null,
  lastResponse: '',
}

const fmtTime = () =>
  new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

function applyTheme(pref) {
  const root = document.documentElement
  const isLight = pref === 'light'
  root.classList.toggle('light', isLight)
  themeToggle.checked = !isLight
  localStorage.setItem('theme', isLight ? 'light' : 'dark')
}

function initTheme() {
  const saved = localStorage.getItem('theme')
  if (saved) return applyTheme(saved)
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  applyTheme(prefersDark ? 'dark' : 'light')
}

themeToggle.addEventListener('change', () => {
  applyTheme(themeToggle.checked ? 'dark' : 'light')
})

function appendMessage(role, text, audioUrl) {
  const wrapper = document.createElement('div')
  wrapper.className = `message ${role}`
  const avatar = document.createElement('div')
  avatar.className = `avatar ${role}`
  avatar.textContent = role === 'user' ? 'U' : 'AI'
  const bubble = document.createElement('div')
  bubble.className = 'bubble'
  const meta = document.createElement('div')
  meta.className = 'meta'
  meta.innerHTML = `<span>${
    role === 'user' ? 'You' : 'Assistant'
  }</span><span>${fmtTime()}</span>`
  const body = document.createElement('div')
  body.textContent = text
  bubble.appendChild(meta)
  bubble.appendChild(body)

  if (audioUrl) {
    const player = document.createElement('audio')
    player.controls = true
    player.src = audioUrl
    player.addEventListener('play', () => setPlayer(player, text))
    bubble.appendChild(player)
  }

  wrapper.appendChild(avatar)
  wrapper.appendChild(bubble)
  messagesEl.appendChild(wrapper)
  messagesEl.scrollTop = messagesEl.scrollHeight
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: { Accept: 'application/json', ...(options.headers || {}) },
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json()
}

async function loadHistory() {
  try {
    const data = await apiFetch('/api/conversation')
    messagesEl.innerHTML = ''
    ;(data.history || []).forEach((m) => appendMessage(m.role, m.content))
  } catch (err) {
    console.error(err)
  }
}

async function sendMessage(message) {
  sendBtn.disabled = true
  try {
    appendMessage('user', message)
    const data = await apiFetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, audio: true }),
    })
    state.lastResponse = data.reply
    appendMessage('assistant', data.reply, data.audio_url)
  } catch (err) {
    appendMessage('assistant', `Error: ${err.message}`)
  } finally {
    sendBtn.disabled = false
    textInput.value = ''
  }
}

sendBtn.addEventListener('click', () => {
  const msg = textInput.value.trim()
  if (!msg) return
  sendMessage(msg)
})

textInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendBtn.click()
  }
})

copyLast.addEventListener('click', async () => {
  if (!state.lastResponse) return
  try {
    await navigator.clipboard.writeText(state.lastResponse)
    copyLast.textContent = 'Copied'
    setTimeout(() => (copyLast.textContent = 'Copy'), 1200)
  } catch (err) {
    console.error('copy failed', err)
  }
})

function setPlayer(el, label) {
  audioPlayer.src = el.src
  audioPlayer.play().catch(() => {})
  audioStatus.textContent = `Playing: ${label.slice(0, 40)}...`
}

audioPlayer.addEventListener('timeupdate', () => {
  if (!audioPlayer.duration) return
  audioProgress.value = (audioPlayer.currentTime / audioPlayer.duration) * 100
})

audioPlayer.addEventListener('ended', () => {
  audioProgress.value = 0
  audioStatus.textContent = 'Playback finished'
})

healthBtn.addEventListener('click', async () => {
  try {
    const res = await apiFetch('/health')
    const info = [
      `Status: ${res.status}`,
      `Provider: ${res.provider} (${res.model || 'N/A'})`,
      `STT: ${res.stt ? 'on' : 'off'} (${res.whisper_model || 'N/A'})`,
      `TTS: ${res.tts ? 'on' : 'off'} (${res.tts_model || 'N/A'})`,
      `FFmpeg: ${res.ffmpeg ? 'available' : 'not found'}`,
    ].join('\n')
    const healthBox = qs('#health-info')
    if (healthBox) healthBox.textContent = info
    audioStatus.textContent = 'Health: ok'
  } catch (err) {
    audioStatus.textContent = 'Health check failed'
  }
})

resetBtn.addEventListener('click', async () => {
  await apiFetch('/api/conversation/reset', { method: 'POST' })
  messagesEl.innerHTML = ''
  transcriptLog.innerHTML = ''
})

function drawWaveform() {
  if (!state.analyser) return
  const ctx = waveform.getContext('2d')
  const bufferLength = state.analyser.fftSize
  const dataArray = new Uint8Array(bufferLength)
  ctx.clearRect(0, 0, waveform.width, waveform.height)

  state.analyser.getByteTimeDomainData(dataArray)
  ctx.lineWidth = 2
  ctx.strokeStyle = '#4ecdc4'
  ctx.beginPath()
  const sliceWidth = waveform.width / bufferLength
  let x = 0
  for (let i = 0; i < bufferLength; i++) {
    const v = dataArray[i] / 128.0
    const y = (v * waveform.height) / 2
    if (i === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
    x += sliceWidth
  }
  ctx.lineTo(waveform.width, waveform.height / 2)
  ctx.stroke()

  requestAnimationFrame(drawWaveform)
}

function startSilenceDetection(source) {
  state.analyser = state.audioContext.createAnalyser()
  state.analyser.fftSize = 512
  source.connect(state.analyser)
  const data = new Uint8Array(state.analyser.frequencyBinCount)

  const checkSilence = () => {
    state.analyser.getByteFrequencyData(data)
    const avg = data.reduce((a, b) => a + b, 0) / data.length
    if (avg < 12 && state.isRecording) {
      if (!state.silenceTimeout) {
        state.silenceTimeout = setTimeout(stopRecording, 1200)
      }
    } else {
      clearTimeout(state.silenceTimeout)
      state.silenceTimeout = null
    }
    if (state.isRecording) requestAnimationFrame(checkSilence)
  }
  checkSilence()
}

async function startRecording() {
  if (state.isRecording) return
  state.isRecording = true
  micBtn.classList.add('recording')
  audioStatus.textContent = 'Recording...'

  state.stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
    },
  })
  state.audioContext = new (window.AudioContext || window.webkitAudioContext)()
  state.sourceNode = state.audioContext.createMediaStreamSource(state.stream)
  state.sampleRate = state.audioContext.sampleRate
  state.samplesCollected = 0
  state.startedAt = performance.now()
  startSilenceDetection(state.sourceNode)
  drawWaveform()

  // Use ScriptProcessorNode for broad compatibility to capture PCM
  const bufferSize = 2048
  const channels = 1
  state.wavBuffers = []
  const processor = state.audioContext.createScriptProcessor(
    bufferSize,
    channels,
    channels
  )
  processor.onaudioprocess = (e) => {
    if (!state.isRecording) return
    const input = e.inputBuffer.getChannelData(0)
    // clone the buffer (Float32Array) before next tick overwrites it
    state.wavBuffers.push(new Float32Array(input))
    state.samplesCollected += input.length
  }
  state.sourceNode.connect(processor)
  processor.connect(state.audioContext.destination) // required in some browsers
  state.processorNode = processor
}

function stopRecording() {
  if (!state.isRecording) return
  state.isRecording = false
  micBtn.classList.remove('recording')
  audioStatus.textContent = 'Processing audio...'
  clearTimeout(state.silenceTimeout)
  state.silenceTimeout = null
  try {
    if (state.processorNode) {
      state.processorNode.disconnect()
    }
    if (state.sourceNode) {
      state.sourceNode.disconnect()
    }
  } catch {}

  // Build WAV blob from captured buffers
  const totalSamples = state.samplesCollected
  const sampleRate =
    state.sampleRate ||
    (state.audioContext && state.audioContext.sampleRate) ||
    48000
  const durationSec = totalSamples / sampleRate
  if (durationSec < 0.6) {
    // Too short to recognize reliably
    audioStatus.textContent = 'Recording too short, try again'
    // Cleanup below, no submit
  }
  const wavBlob =
    durationSec >= 0.6 ? encodeWAV(state.wavBuffers, sampleRate, 16000) : null

  // Cleanup audio resources
  try {
    if (state.stream) {
      state.stream.getTracks().forEach((t) => t.stop())
    }
    if (state.audioContext) {
      state.audioContext.close()
    }
  } catch {}
  state.stream = null
  state.sourceNode = null
  state.processorNode = null
  state.audioContext = null
  state.wavBuffers = []
  state.samplesCollected = 0
  state.sampleRate = 0
  state.startedAt = 0

  if (wavBlob) submitRecording(wavBlob)
}

micBtn.addEventListener('mousedown', startRecording)
micBtn.addEventListener('mouseup', stopRecording)
micBtn.addEventListener(
  'mouseleave',
  () => state.isRecording && stopRecording()
)
micBtn.addEventListener('touchstart', (e) => {
  e.preventDefault()
  startRecording()
})
micBtn.addEventListener('touchend', (e) => {
  e.preventDefault()
  stopRecording()
})

function floatTo16BitPCM(float32Array) {
  const len = float32Array.length
  const buffer = new ArrayBuffer(len * 2)
  const view = new DataView(buffer)
  let offset = 0
  for (let i = 0; i < len; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, float32Array[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Uint8Array(buffer)
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i))
  }
}

function writeWavHeader(view, sampleRate, dataBytes, channels = 1) {
  // ChunkID 'RIFF'
  writeString(view, 0, 'RIFF')
  // ChunkSize = 36 + Subchunk2Size
  view.setUint32(4, 36 + dataBytes, true)
  // Format 'WAVE'
  writeString(view, 8, 'WAVE')
  // Subchunk1ID 'fmt '
  writeString(view, 12, 'fmt ')
  // Subchunk1Size (16 for PCM)
  view.setUint32(16, 16, true)
  // AudioFormat (1 = PCM)
  view.setUint16(20, 1, true)
  // NumChannels
  view.setUint16(22, channels, true)
  // SampleRate
  view.setUint32(24, sampleRate, true)
  // ByteRate = SampleRate * NumChannels * BitsPerSample/8
  const byteRate = sampleRate * channels * 2
  view.setUint32(28, byteRate, true)
  // BlockAlign = NumChannels * BitsPerSample/8
  view.setUint16(32, channels * 2, true)
  // BitsPerSample
  view.setUint16(34, 16, true)
  // Subchunk2ID 'data'
  writeString(view, 36, 'data')
  // Subchunk2Size = NumSamples * NumChannels * BitsPerSample/8
  view.setUint32(40, dataBytes, true)
}

function resampleFloat32(input, fromRate, toRate) {
  if (fromRate === toRate) return input
  const ratio = fromRate / toRate
  const newLength = Math.max(1, Math.round(input.length / ratio))
  const output = new Float32Array(newLength)
  for (let i = 0; i < newLength; i++) {
    const idx = i * ratio
    const idx0 = Math.floor(idx)
    const idx1 = Math.min(idx0 + 1, input.length - 1)
    const frac = idx - idx0
    output[i] = input[idx0] * (1 - frac) + input[idx1] * frac
  }
  return output
}

function encodeWAV(buffers, sampleRate, targetRate = 16000) {
  // Merge Float32 buffers
  const length = buffers.reduce((acc, b) => acc + b.length, 0)
  const merged = new Float32Array(length)
  let offset = 0
  for (const b of buffers) {
    merged.set(b, offset)
    offset += b.length
  }
  let resampled = resampleFloat32(merged, sampleRate, targetRate)
  // Normalize to avoid very low amplitude
  let maxAbs = 0
  for (let i = 0; i < resampled.length; i++) {
    const v = Math.abs(resampled[i])
    if (v > maxAbs) maxAbs = v
  }
  if (maxAbs > 0 && maxAbs < 0.2) {
    const gain = Math.min(5, 0.9 / maxAbs)
    const out = new Float32Array(resampled.length)
    for (let i = 0; i < resampled.length; i++) out[i] = resampled[i] * gain
    resampled = out
  }
  const pcm16 = floatTo16BitPCM(resampled)
  const header = new ArrayBuffer(44)
  const view = new DataView(header)
  writeWavHeader(view, targetRate, pcm16.byteLength, 1)
  const wavBytes = new Uint8Array(44 + pcm16.byteLength)
  wavBytes.set(new Uint8Array(header), 0)
  wavBytes.set(pcm16, 44)
  return new Blob([wavBytes], { type: 'audio/wav' })
}

async function submitRecording(blob) {
  if (!blob) return
  const form = new FormData()
  form.append('file', blob, 'recording.wav')
  try {
    const lang = (navigator.language || 'en-US').replace('_', '-')
    form.append('language', lang)
  } catch {}

  try {
    const data = await apiFetch('/api/speech-to-text', {
      method: 'POST',
      body: form,
    })
    const line = document.createElement('div')
    line.textContent = data.transcript || '(no speech detected)'
    transcriptLog.appendChild(line)
    transcriptLog.scrollTop = transcriptLog.scrollHeight
    if (data.transcript) sendMessage(data.transcript)
    audioStatus.textContent = 'Transcribed and sent'
  } catch (err) {
    audioStatus.textContent = 'STT failed'
    appendMessage('assistant', `STT error: ${err.message}`)
  }
}

window.addEventListener('load', () => {
  initTheme()
  loadHistory()
})
