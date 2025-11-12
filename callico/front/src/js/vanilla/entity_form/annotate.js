import { bootFieldGroups } from './base'
import { displayConfidenceTag } from '../utils/confidence_tag.js'
import { bootUncertainty } from '../utils/handle_uncertainty.js'
import * as api from '../../api.js'
import { getUserTaskAnnotation, setUserTaskAnnotation, displayWarning } from '../annotations/storage.js'

const saveUserTaskAnnotation = (userTaskID, parentID) => {
  const storedAnnotations = getUserTaskAnnotation(userTaskID, parentID) || {}
  const fields = document.querySelectorAll('.annotation-form .annotation-field')
  const values = {
    ...storedAnnotations,
    ...Array.from(fields).reduce((annotations, field, index) => (
      {
        ...annotations,
        [JSON.stringify([field.getAttribute('entity_type'), field.getAttribute('instruction')])]: {
          value: field.value,
          uncertain: document.getElementById(`id_form-${index}-uncertain`).getAttribute('value')
        }
      }), {})
  }
  setUserTaskAnnotation(userTaskID, parentID, values)
}

const updateDropdownOptions = async (field, dropdownContent, warningContent) => {
  const dropdownItems = []
  const values = await api.listAuthorityValues(field.getAttribute('authority_id'), field.value)

  // When no authority value is returned, we display a warning message
  if (!values.length) {
    const dropdownItemDiv = document.createElement('div')
    dropdownItemDiv.classList.add('dropdown-item')

    const messageDiv = document.createElement('div')
    messageDiv.classList.add('message', 'is-warning', 'is-small')
    dropdownItemDiv.appendChild(messageDiv)

    const messageBodyDiv = document.createElement('div')
    messageBodyDiv.classList.add('message-body')
    messageBodyDiv.textContent = warningContent
    messageDiv.appendChild(messageBodyDiv)

    dropdownItems.push(dropdownItemDiv)
  // Otherwise, we display all the choices we received in the dropdown
  } else {
    values.forEach(value => {
      const dropdownItemLink = document.createElement('a')
      dropdownItemLink.classList.add('dropdown-item')
      dropdownItemLink.setAttribute('value', value.value)
      dropdownItemLink.textContent = value.value
      dropdownItems.push(dropdownItemLink)

      // When clicking on an item, we update the value of our input
      dropdownItemLink.addEventListener('click', () => {
        field.value = dropdownItemLink.getAttribute('value')
        field.dispatchEvent(new Event('input'))
      })
    })
  }

  // Removing existing options from the dropdown
  dropdownContent.replaceChildren()
  // Adding the refreshed options instantly after the removal to avoid flickering
  dropdownContent.append(...dropdownItems)
}

const initFields = (userTaskID, parentID, warningContent) => {
  const storedAnnotations = getUserTaskAnnotation(userTaskID, parentID) || {}

  document.querySelectorAll('.annotation-form .annotation-field').forEach((field, index) => {
    // Update textarea value from the stored annotation
    const entityType = field.getAttribute('entity_type')
    const entityInstruction = field.getAttribute('instruction')
    const entity = storedAnnotations[JSON.stringify([entityType, entityInstruction])]
    const uncertainField = document.getElementById(`id_form-${index}-uncertain`)
    if (entity && (field.value !== entity.value || uncertainField.getAttribute('value') !== entity.uncertain)) {
      field.value = entity.value
      uncertainField.setAttribute('value', entity.uncertain)
      displayWarning(userTaskID, parentID)
    }

    // Update field events
    field.addEventListener('input', () => { saveUserTaskAnnotation(userTaskID, parentID) })

    // Display the prediction confidence if available
    const fieldLabel = field.closest('div.field').querySelector('label.label')
    displayConfidenceTag(field, fieldLabel)

    // Display the annotation help text if provided
    const helpText = field.getAttribute('help_text')
    if (helpText) {
      const dropdownDiv = document.createElement('div')
      dropdownDiv.classList.add('dropdown', 'is-hoverable', 'pl-1')
      dropdownDiv.innerHTML = '<div class="dropdown-trigger"><span class="icon has-text-info"><i class="fas fa-question-circle"></i></span></div>'

      const dropdownMenuDiv = document.createElement('div')
      dropdownMenuDiv.classList.add('dropdown-menu')
      dropdownMenuDiv.setAttribute('role', 'menu')
      dropdownMenuDiv.style.zIndex = 10

      const dropdownContentDiv = document.createElement('div')
      dropdownContentDiv.classList.add('dropdown-content', 'p-0')

      const dropdownItemDiv = document.createElement('div')
      dropdownItemDiv.classList.add('dropdown-item', 'has-background-info-light', 'has-text-info-dark', 'break-word')
      dropdownItemDiv.textContent = helpText

      dropdownContentDiv.appendChild(dropdownItemDiv)
      dropdownMenuDiv.appendChild(dropdownContentDiv)
      dropdownDiv.appendChild(dropdownMenuDiv)
      fieldLabel.appendChild(dropdownDiv)
    }

    // Initialize the dropdown for fields that are associated to an authority
    const authorityId = field.getAttribute('authority_id')
    if (authorityId) {
      const dropdownDiv = document.createElement('div')
      dropdownDiv.classList.add('dropdown')
      dropdownDiv.style.width = '100%'
      field.parentElement.insertBefore(dropdownDiv, field)

      const dropdownTriggerDiv = document.createElement('div')
      dropdownTriggerDiv.classList.add('dropdown-trigger')
      dropdownTriggerDiv.style.width = '100%'
      dropdownDiv.appendChild(dropdownTriggerDiv)

      const dropdownMenuDiv = document.createElement('div')
      dropdownMenuDiv.classList.add('dropdown-menu')
      dropdownMenuDiv.role = 'menu'
      dropdownMenuDiv.style.zIndex = 8
      dropdownDiv.appendChild(dropdownMenuDiv)

      const dropdownContentDiv = document.createElement('div')
      dropdownContentDiv.classList.add('dropdown-content')
      dropdownContentDiv.style.maxHeight = '15vh'
      dropdownContentDiv.style.overflowY = 'auto'
      dropdownMenuDiv.appendChild(dropdownContentDiv)

      // Once the dropdown is properly instantiated and placed, move the field in it
      dropdownTriggerDiv.appendChild(field)

      // Trigger the update a first time to fill the dropdown at initialization
      updateDropdownOptions(field, dropdownContentDiv, warningContent)

      // Listen to events on the input to expand the dropdown or not
      if (field === document.activeElement) dropdownDiv.classList.add('is-active')
      field.addEventListener('click', () => { dropdownDiv.classList.add('is-active') })
      field.addEventListener('focus', () => { dropdownDiv.classList.add('is-active') })
      field.addEventListener('focusout', () => { setTimeout(() => { dropdownDiv.classList.remove('is-active') }, 150) })

      // Listen to the `input` event to reload the authority value list from the backend
      let timeout = null
      field.addEventListener('input', (event) => {
        if (timeout !== null) {
          clearTimeout(timeout)
        }

        // Wait 0.3 seconds before reaching the backend once again
        timeout = setTimeout(() => {
          updateDropdownOptions(field, dropdownContentDiv, warningContent)
        }, 300)
      })
    }
  })
}

export const bootEntityFormAnnotate = (userTaskID, parentID, warningContent) => {
  initFields(userTaskID, parentID, warningContent)
  bootUncertainty(userTaskID, parentID, saveUserTaskAnnotation)

  const form = document.querySelector('.annotation-form')
  bootFieldGroups(form, '.annotation-field', 'mb-4', '.field')
}
