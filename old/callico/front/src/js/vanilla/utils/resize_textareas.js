const _resizeHeight = (textarea) => {
  textarea.style.height = 0
  textarea.style.height = (textarea.scrollHeight) + 'px'
}

const initTextareas = () => {
  document.querySelectorAll('textarea').forEach((textarea) => {
    // Allow to resize the textarea to match the provided content
    textarea.style.overflowY = 'hidden'
    textarea.style.minHeight = (textarea.offsetHeight) + 'px'
    _resizeHeight(textarea)

    textarea.addEventListener('input', () => {
      _resizeHeight(textarea)
    })
  })
}

export const bootTextareaSizes = () => {
  initTextareas()
}
