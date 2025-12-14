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
  mediaRecorder: null,
  audioChunks: [],
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
    audioStatus.textContent = `Health: ok | Gemini ${
      res.gemini ? 'on' : 'off'
    } (${res.gemini_model || 'N/A'}) | STT ${res.stt ? 'on' : 'off'} (${
      res.whisper_model
    }) | TTS ${res.tts ? 'on' : 'off'} (${res.tts_model})`
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

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  state.audioContext = new (window.AudioContext || window.webkitAudioContext)()
  const source = state.audioContext.createMediaStreamSource(stream)
  startSilenceDetection(source)
  drawWaveform()

  state.mediaRecorder = new MediaRecorder(stream)
  state.audioChunks = []
  state.mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) state.audioChunks.push(e.data)
  }
  state.mediaRecorder.onstop = () => {
    stream.getTracks().forEach((t) => t.stop())
    state.audioContext.close()
    state.audioContext = null
    submitRecording()
  }
  state.mediaRecorder.start()
}

function stopRecording() {
  if (!state.isRecording || !state.mediaRecorder) return
  state.isRecording = false
  micBtn.classList.remove('recording')
  audioStatus.textContent = 'Processing audio...'
  clearTimeout(state.silenceTimeout)
  state.silenceTimeout = null
  state.mediaRecorder.stop()
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

async function submitRecording() {
  if (!state.audioChunks.length) return
  const blob = new Blob(state.audioChunks, { type: 'audio/webm' })
  const form = new FormData()
  form.append('file', blob, 'recording.webm')

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
