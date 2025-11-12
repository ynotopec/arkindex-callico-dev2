// eslint-disable-next-line import/no-named-as-default
import Sortable from 'sortablejs'

const FORM_NAME_PREFIX = 'form'
const FORM_ID_PREFIX = 'id_form'
const FORM_ATTRIBUTES = ['name', 'id', 'for']
const FORM_TOTAL_ID = 'id_form-TOTAL_FORMS'
const FORM_INITAL_ID = 'id_form-INITIAL_FORMS'

const updateAllFieldsetAttributes = (formset) => {
  formset.querySelectorAll('fieldset:not(.is-hidden)').forEach((fieldset, index) => {
    updateFieldsetAttributes(fieldset, index)
  })
}

const updateFieldsetAttributes = (fieldset, index) => {
  FORM_ATTRIBUTES.forEach(attr => {
    fieldset.querySelectorAll(`[${attr}]`).forEach(element => {
      const newValue = element.getAttribute(attr).replace(/(.+)-.+-(.+)/gm, `$1-${index}-$2`)
      element.setAttribute(attr, newValue)
    })
  })
}

const initDeleteButton = (formset) => {
  formset.querySelectorAll('.icon.has-text-danger').forEach(button => {
    button.addEventListener('click', removeFieldset)
  })
}

const addEmptyFieldset = () => {
  const emptyFieldset = document.querySelector('fieldset.is-hidden')
  const fieldset = emptyFieldset.cloneNode(true)
  fieldset.classList.remove('is-hidden')

  // Special case for Entity campaigns to have a random color per fieldset
  const entityColorInput = fieldset.querySelector('input[type=color]')
  if (entityColorInput) entityColorInput.value = '#' + Math.floor(Math.random() * 16777215).toString(16)

  // Update the total forms input
  const input = document.getElementById(FORM_TOTAL_ID)
  const previousNbForms = input.getAttribute('value')
  input.setAttribute('value', parseInt(previousNbForms) + 1)

  // Replace the form prefix by the index of the item
  updateFieldsetAttributes(fieldset, previousNbForms)

  return fieldset
}

export const removeFieldset = (evt) => {
  const fieldset = evt.target.closest('fieldset')
  const formset = fieldset.closest('.formset')
  fieldset.remove()

  // Update each index of the existing forms
  updateAllFieldsetAttributes(formset)

  // Update the total forms input
  const input = document.getElementById(FORM_TOTAL_ID)
  const previousNbForms = input.getAttribute('value')
  input.setAttribute('value', parseInt(previousNbForms) - 1)
}

export const initDynamicFormset = () => {
  // Force the value to zero to accept empty forms even when there were initial values
  const input = document.getElementById(FORM_INITAL_ID)
  if (!input) return

  input.setAttribute('value', 0)

  // Update each "Delete field" button
  const formset = input.closest('.formset')
  initDeleteButton(formset)

  // Update each "grabbable" button
  Sortable.create(formset, {
    handle: '.is-grabbable',
    animation: 150,
    onEnd: () => updateAllFieldsetAttributes(formset)
  })

  // Update the "Add field" button
  const button = formset.querySelector('button.is-success[type="button"]')
  if (!button) return

  button.addEventListener('click', () => {
    const fieldset = addEmptyFieldset()

    initDeleteButton(fieldset)

    formset.insertBefore(fieldset, button.previousElementSibling)
  })
}

export const getForm = () => {
  const input = document.getElementById(FORM_INITAL_ID)
  return input.closest('form[method="post"]')
}

export const initFormset = (items, formatValue) => {
  const input = document.getElementById(FORM_TOTAL_ID)
  const form = input.closest('form[method="post"]')

  form.addEventListener('submit', () => {
    /*
     * We don't know how many forms we will have at the end.
     * So we have to add one form per item ourselves.
     * To do this, Django provides an empty form with a specific prefix that must be replaced by an index.
     */
    items.forEach((item, index) => {
      const fieldset = addEmptyFieldset()

      // Update input values
      for (const key in item) {
        /*
         * To return a list of values, we need one input per value.
         * By default, Django does not provide any input in an empty form,
         * so we have to create them ourselves.
         */
        const value = formatValue(key, item[key])
        if (Array.isArray(value)) {
          value.forEach((val, subindex) => {
            const input = document.createElement('input')
            input.classList.add('is-hidden')
            input.setAttribute('id', `${FORM_ID_PREFIX}-${index}-${key}_${subindex}`)
            input.setAttribute('name', `${FORM_NAME_PREFIX}-${index}-${key}`)
            input.setAttribute('value', val)
            fieldset.appendChild(input)
          })
        } else {
          const input = fieldset.querySelector(`input[id*=${key}]`)
          input.setAttribute('value', value)
        }
      }

      form.prepend(fieldset)
    })
  }, { once: true })
}
