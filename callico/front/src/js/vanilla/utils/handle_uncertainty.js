const CERTAIN_VALUE = 'False'
const UNCERTAIN_VALUE = 'True'

const createUncertainButton = (annotationField) => {
  const control = annotationField.closest('div.control')

  const wrapperDiv = document.createElement('div')
  wrapperDiv.classList.add('is-flex', 'is-align-items-center')
  // Field with predefined choices (which is inside a span)
  if (annotationField.nodeName === 'SELECT') {
    wrapperDiv.appendChild(annotationField.parentElement)
  // Field linked to an authority (which is inside the trigger of a dropdown)
  } else if (annotationField.getAttribute('authority_id')) {
    wrapperDiv.appendChild(annotationField.parentElement.parentElement)
  } else {
    wrapperDiv.appendChild(annotationField)
  }

  const uncertainButton = document.createElement('button')
  uncertainButton.setAttribute('type', 'button')
  uncertainButton.classList.add('button', 'ml-1', 'is-small')
  uncertainButton.innerHTML = '<span class="icon is-small"><i class="fas fa-exclamation"></i></span>'
  wrapperDiv.appendChild(uncertainButton)

  control.insertAdjacentElement('afterbegin', wrapperDiv)

  return uncertainButton
}

const markCertain = (annotationField, uncertainField, button) => {
  const CERTAIN_TITLE = document.getElementById('certain-button-translated-title').textContent

  uncertainField.setAttribute('value', CERTAIN_VALUE)
  annotationField.classList.remove('is-italic')
  button.classList.remove('is-danger', 'is-italic')
  button.classList.add('is-warning', 'is-invisible')
  button.setAttribute('title', CERTAIN_TITLE)
}

const markUncertain = (annotationField, uncertainField, button) => {
  const UNCERTAIN_TITLE = document.getElementById('uncertain-button-translated-title').textContent

  uncertainField.setAttribute('value', UNCERTAIN_VALUE)
  annotationField.classList.add('is-italic')
  button.classList.remove('is-warning')
  button.classList.add('is-danger', 'is-italic')
  button.setAttribute('title', UNCERTAIN_TITLE)
}

export const bootUncertainty = (userTaskID, parentID, saveUserTaskAnnotation = (userTaskID, parentID) => {}) => {
  document.querySelectorAll('.annotation-form .annotation-field').forEach((annotationField, index) => {
    // Special class added to have the uncertain button on the same line as the textarea
    if (annotationField.nodeName === 'TEXTAREA') annotationField.classList.add('auto-width')

    // The button to activate/deactivate uncertainty on the annotation field
    const uncertainButton = createUncertainButton(annotationField)

    // The hidden form field to report uncertainty
    const uncertainField = document.getElementById(`id_form-${index}-uncertain`)

    // Initialize the display with stored values from parent annotation
    const updateDisplay = uncertainField.getAttribute('value') === UNCERTAIN_VALUE ? markUncertain : markCertain
    updateDisplay(annotationField, uncertainField, uncertainButton)

    // Upon clicking on the uncertain button, we should transform the display and update the hidden form field value accordingly
    uncertainButton.addEventListener('click', () => {
      const updateDisplay = uncertainField.getAttribute('value') === CERTAIN_VALUE ? markUncertain : markCertain
      updateDisplay(annotationField, uncertainField, uncertainButton)
      saveUserTaskAnnotation(userTaskID, parentID)
    })

    // Do show the button when the field is focused
    annotationField.addEventListener('focus', () => { uncertainButton.classList.remove('is-invisible') })

    // Do make the button invisible when losing focus on either the field or the button
    annotationField.addEventListener('blur', e => {
      if (e.relatedTarget === uncertainButton || !uncertainButton.classList.contains('is-warning')) return
      uncertainButton.classList.add('is-invisible')
    })
    uncertainButton.addEventListener('blur', e => {
      if (e.relatedTarget === annotationField || !uncertainButton.classList.contains('is-warning')) return
      uncertainButton.classList.add('is-invisible')
    })
  })

  // Focus the first annotation field by default
  document.querySelector('.annotation-form .annotation-field').focus()
}
