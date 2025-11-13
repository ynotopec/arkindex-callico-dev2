import Mousetrap from 'mousetrap'

const letter = (number) => {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz'.split('')
  return alphabet[number - 10]
}

const shortcut = (value) => {
  return (parseInt(value) < 10 ? value : letter(value))
}

const initKeyboardShorcuts = () => {
  const form = document.getElementById('classification-form')
  form.querySelectorAll('div.button-container').forEach(container => {
    const button = container.querySelector('input')
    const buttonIndex = button.attributes.index.value
    if (parseInt(buttonIndex) < 36) {
      const tag = container.querySelector('span')
      const key = shortcut(buttonIndex)
      tag.append(key)
      Mousetrap.bind(key, function () { button.click() })
    }
  })
}

export const bootClassificationAnnotate = () => {
  initKeyboardShorcuts()

  window.addEventListener('submit', () => {
    Mousetrap.reset()
  })
}
