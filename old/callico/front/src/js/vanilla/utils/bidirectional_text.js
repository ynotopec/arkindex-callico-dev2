import Mousetrap from 'mousetrap'

// Right-to-Left Mark
const RLM = '\u200F'

const initKeyboardShorcut = () => {
  document.querySelectorAll('.rtl-text').forEach(textarea => {
    Mousetrap(textarea).bind('ctrl+left', () => {
      const textLength = textarea.value.length
      if (!textLength || textarea.value[textLength - 1] === RLM) return
      textarea.value += RLM
    })
  })
}

export const bootBidiText = () => {
  initKeyboardShorcut()

  window.addEventListener('submit', () => {
    Mousetrap.reset()
  })
}
