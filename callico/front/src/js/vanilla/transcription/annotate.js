import { displayConfidenceTag } from '../utils/confidence_tag.js'
import { bootUncertainty } from '../utils/handle_uncertainty.js'
import { dispatchCarouselTriggerSelection, CAROUSEL_SELECT_ELEMENT_EVENT } from '../events/carousel.js'
import { dispatchSelectElement, dispatchUnselectElement, SELECT_ELEMENT_EVENT } from '../events/interactive_image.js'
import { getUserTaskAnnotation, setUserTaskAnnotation, displayWarning } from '../annotations/storage.js'

const _focus = (textarea, hint) => {
  dispatchSelectElement(textarea.id)
  dispatchCarouselTriggerSelection(textarea.id)

  if (!hint) return
  hint.classList.remove('is-invisible')
  hint.textContent = textarea.getAttribute('hidden-label')
}

const _unfocus = (textarea, hint) => {
  dispatchUnselectElement(textarea.id)

  if (!hint) return
  hint.classList.add('is-invisible')
}

const saveUserTaskAnnotation = (userTaskID, parentID) => {
  const storedAnnotations = getUserTaskAnnotation(userTaskID, parentID) || {}
  const textareas = document.querySelectorAll('textarea')
  const values = {
    ...storedAnnotations,
    ...Array.from(textareas).reduce((annotations, textarea, index) => (
      {
        ...annotations,
        [textarea.id]: {
          value: textarea.value,
          uncertain: document.getElementById(`id_form-${index}-uncertain`).getAttribute('value')
        }
      }), {})
  }
  setUserTaskAnnotation(userTaskID, parentID, values)
}

const initTextareas = (userTaskID, parentID) => {
  const LIGHT_DISPLAY_HINT = document.getElementById('light-display-hint')
  const storedAnnotations = getUserTaskAnnotation(userTaskID, parentID) || {}

  document.querySelectorAll('textarea').forEach((textarea, index) => {
    // Update textarea value from the stored annotation
    const transcription = storedAnnotations[textarea.id]
    const uncertainField = document.getElementById(`id_form-${index}-uncertain`)
    if (transcription && (textarea.value !== transcription.value || uncertainField.getAttribute('value') !== transcription.uncertain)) {
      textarea.value = transcription.value
      document.getElementById(`id_form-${index}-uncertain`).setAttribute('value', transcription.uncertain)
      displayWarning(userTaskID, parentID)
    }

    // Update textarea events
    if (textarea === document.activeElement) _focus(textarea, LIGHT_DISPLAY_HINT)
    textarea.addEventListener('click', () => { _focus(textarea, LIGHT_DISPLAY_HINT) })
    textarea.addEventListener('focus', () => { _focus(textarea, LIGHT_DISPLAY_HINT) })
    textarea.addEventListener('focusout', () => { _unfocus(textarea, LIGHT_DISPLAY_HINT) })
    textarea.addEventListener('input', () => { saveUserTaskAnnotation(userTaskID, parentID) })
  })
}

const initLibraryEvents = () => {
  document.addEventListener(SELECT_ELEMENT_EVENT, (evt) => {
    const elementId = evt.detail
    const textarea = document.getElementById(elementId)
    if (!textarea || textarea === document.activeElement) return
    textarea.focus()
  })

  document.addEventListener(CAROUSEL_SELECT_ELEMENT_EVENT, (evt) => {
    const elementId = evt.detail.id
    const textarea = document.getElementById(elementId)
    if (!textarea || textarea === document.activeElement) return
    textarea.focus()
  })
}

export const bootTranscriptionAnnotate = (userTaskID, parentID) => {
  initTextareas(userTaskID, parentID)
  initLibraryEvents()
  bootUncertainty(userTaskID, parentID, saveUserTaskAnnotation)

  document.querySelectorAll('textarea').forEach((textarea, index) => {
    // Display the prediction confidence if available
    let confidenceContainer = textarea.closest('div.field').querySelector('label.label')
    if (textarea.classList.contains('light-input')) {
      confidenceContainer = document.createElement('div')
      confidenceContainer.classList.add('floating-confidence')
      textarea.parentElement.insertBefore(confidenceContainer, textarea)
    }
    displayConfidenceTag(textarea, confidenceContainer)
  })
}
