import { dispatchCarouselTriggerSelection, CAROUSEL_SELECT_ELEMENT_EVENT } from '../events/carousel.js'
import { dispatchUpdateSelectedElements, dispatchUnselectElement, SELECT_ELEMENT_EVENT, UNSELECT_ELEMENT_EVENT } from '../events/interactive_image.js'

const MESSAGE_ATTRIBUTE = 'answer-element-id'
const FOCUS_CLASS = 'is-info'

const _focusAllMessages = (elementId = null) => {
  // Unfocus every other elements
  document.querySelectorAll(`.dropdown-toggle-content .message.${FOCUS_CLASS}`).forEach((message) => {
    message.classList.remove(FOCUS_CLASS)
  })

  if (!elementId) return

  // Only focus one element (with several annotations) at once
  document.querySelectorAll(`.dropdown-toggle-content .message[${MESSAGE_ATTRIBUTE}="${elementId}"]`).forEach((message) => {
    message.classList.add(FOCUS_CLASS)
  })
}

const initMessages = () => {
  document.querySelectorAll('.dropdown-toggle-content .message').forEach((message) => {
    const elementId = message.getAttribute(MESSAGE_ATTRIBUTE)
    message.addEventListener('click', () => {
      // Allow to unfocus a message
      if (message.classList.contains(FOCUS_CLASS)) {
        dispatchUnselectElement(elementId)
      } else {
        _focusAllMessages(elementId)
        dispatchUpdateSelectedElements([elementId])
        dispatchCarouselTriggerSelection(elementId)
      }
    })
  })
}

const _getMessage = (elementId) => {
  // Select the first open version
  let message = document.querySelector(`.dropdown-toggle-content:not(.is-hidden) .message[${MESSAGE_ATTRIBUTE}="${elementId}"]`)

  if (!message) {
    // Select the first version
    message = document.querySelector(`.dropdown-toggle-content .message[${MESSAGE_ATTRIBUTE}="${elementId}"]`)
    if (!message) return
    // Simulate a click to open the dropdown
    const dropdown = message.closest('.dropdown-toggle').querySelector('.dropdown-toggle-title')
    dropdown.click()
  }

  return message
}

const _selectElement = (elementId) => {
  // Check if the message is already focused
  const focusedMessages = document.querySelectorAll(`.dropdown-toggle-content .message.${FOCUS_CLASS}`)
  if ([...focusedMessages].map(message => message.getAttribute(MESSAGE_ATTRIBUTE)).includes(elementId)) return

  _focusAllMessages(elementId)
  dispatchUpdateSelectedElements([elementId])

  // Focus on the message containing the answer
  const messageToFocus = _getMessage(elementId)
  if (!messageToFocus) return
  messageToFocus.scrollIntoView({ block: 'center', inline: 'center' })
}

const _unselectElement = (elementId) => {
  // Check if the message is already unfocused
  const focusedMessages = document.querySelectorAll(`.dropdown-toggle-content .message.${FOCUS_CLASS}`)
  if (![...focusedMessages].map(message => message.getAttribute(MESSAGE_ATTRIBUTE)).includes(elementId)) return

  _focusAllMessages()

  // Focus on the message containing the answer
  const messageToFocus = _getMessage(elementId)
  if (!messageToFocus) return
  messageToFocus.scrollIntoView({ block: 'center', inline: 'center' })
}

const initLibraryEvents = () => {
  document.addEventListener(SELECT_ELEMENT_EVENT, (evt) => {
    const elementId = evt.detail
    _selectElement(elementId)
  })

  document.addEventListener(UNSELECT_ELEMENT_EVENT, (evt) => {
    const elementId = evt.detail
    _unselectElement(elementId)
  })

  document.addEventListener(CAROUSEL_SELECT_ELEMENT_EVENT, (evt) => {
    const elementId = evt.detail.id
    _selectElement(elementId)
  })
}

export const bootTranscriptionUserTaskDetails = () => {
  initMessages()
  initLibraryEvents()
}
