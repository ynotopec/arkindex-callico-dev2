import { organizeLeftOrRightFields } from '../utils/left_or_right.js'

const initCheckbox = (checkbox) => {
  const choicesInput = checkbox.parentElement.parentElement.parentElement.nextElementSibling

  checkbox.addEventListener('change', () => {
    if (checkbox.checked) {
      choicesInput.classList.remove('is-hidden')
    } else {
      choicesInput.classList.add('is-hidden')
    }
  })

  // The form was submitted, but with errors
  if (choicesInput.querySelector('span.help.is-danger') || checkbox.checked) {
    choicesInput.classList.remove('is-hidden')
  // An initial value is set in the allowed annotations text input
  } else if (choicesInput.querySelector('input[type=text]').value) {
    checkbox.click()
  // Hide the allowed annotations text input by default
  } else {
    choicesInput.classList.add('is-hidden')
  }
}

const initAuthorityOrCustomChoices = (allowCustomCheckbox, orSpanContent) => {
  const AUTHORITY_FIELD = document.getElementById('id_from_authority').closest('div.field')
  const ALLOW_CUSTOM_FIELD = allowCustomCheckbox.closest('div.field')
  const CUSTOM_CHOICES_FIELD = document.getElementById('id_predefined_choices').closest('div.field')
  const REGEXP_FIELD = document.getElementById('id_validation_regex').closest('div.field')

  organizeLeftOrRightFields([AUTHORITY_FIELD], [ALLOW_CUSTOM_FIELD, CUSTOM_CHOICES_FIELD], orSpanContent, REGEXP_FIELD)
}

export const bootEntityFormFieldForm = (orSpanContent) => {
  const checkbox = document.getElementById('id_allow_predefined_choices')
  initCheckbox(checkbox)

  initAuthorityOrCustomChoices(checkbox, orSpanContent)
}
