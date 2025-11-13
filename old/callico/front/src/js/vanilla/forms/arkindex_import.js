import BulmaTagsInput from '@creativebulma/bulma-tagsinput'
import { confirmEnterKeySubmit } from '../utils/enter_key_submit.js'
import { organizeLeftOrRightFields } from '../utils/left_or_right.js'

const updateEntityCheckboxes = () => {
  const TRANSCRIPTION_CHECKBOXES = document.querySelectorAll('label.radio input[type=checkbox][name=transcriptions]')
  const ENTITY_CHECKBOXES = document.querySelectorAll('label.radio input[type=checkbox][name=entities]')

  if (Array.from(TRANSCRIPTION_CHECKBOXES).some(checkbox => checkbox.checked)) {
    // Enable entity checkboxes
    ENTITY_CHECKBOXES.forEach(checkbox => {
      checkbox.disabled = false
      checkbox.parentElement.removeAttribute('disabled')
    })
  } else {
    // Disable entity checkboxes
    ENTITY_CHECKBOXES.forEach(checkbox => {
      checkbox.disabled = true
      checkbox.checked = false
      checkbox.parentElement.setAttribute('disabled', true)
      checkbox.dispatchEvent(new Event('change'))
    })
  }
}

const updateOrderInSpans = (checkboxes, selectedItems) => {
  checkboxes.forEach(checkbox => {
    let orderHint = checkbox.previousSibling
    if (orderHint === null || orderHint.nodeName !== 'SPAN') {
      orderHint = document.createElement('span')
      orderHint.classList.add('tag', 'is-rounded', 'mr-2', 'sortable-checkbox-span')
      checkbox.parentElement.insertBefore(orderHint, checkbox)
    }

    const index = selectedItems.indexOf(checkbox)
    if (index === -1) {
      orderHint.innerText = '−'
      orderHint.classList.remove('is-primary')
    } else {
      orderHint.innerText = index + 1
      orderHint.classList.add('is-primary')
    }
  })
}

const initSortableWidget = (inputName) => {
  const CHECKBOXES = document.querySelectorAll(`label.radio input[type=checkbox][name=${inputName}]`)
  const SELECTED_ITEMS = []

  updateOrderInSpans(CHECKBOXES, SELECTED_ITEMS)

  CHECKBOXES.forEach(checkbox => {
    // Reset a wrongly preserved checked state if necessary
    checkbox.checked = false

    const radioLabel = checkbox.parentElement
    const controlDiv = radioLabel.parentElement
    const helpText = controlDiv.querySelector('p.help')

    checkbox.addEventListener('change', () => {
      // Upon selection/deselection, we need to update the checkboxes order
      if (checkbox.checked) {
        const firstCheckboxNotSelected = SELECTED_ITEMS.length ? SELECTED_ITEMS[SELECTED_ITEMS.length - 1].parentElement.nextSibling : controlDiv.firstChild
        if (SELECTED_ITEMS.indexOf(checkbox) === -1) SELECTED_ITEMS.push(checkbox)
        controlDiv.insertBefore(radioLabel, firstCheckboxNotSelected)
      } else {
        const index = SELECTED_ITEMS.indexOf(checkbox)
        if (index !== -1) SELECTED_ITEMS.splice(index, 1)
        controlDiv.insertBefore(radioLabel, helpText)
      }
      updateOrderInSpans(CHECKBOXES, SELECTED_ITEMS)
    })
  })
}

const initCustomSelect = (select) => {
  select.setAttribute('data-type', 'tags')
  select.setAttribute('data-selectable', 'false')
  select.setAttribute('data-case-sensitive', 'false')
  const input = new BulmaTagsInput(select)
  input.flush()

  return input
}

const initElementsWorkerRunWidget = () => {
  const ELEMENTS_WR_WIDGET = document.getElementById('elements_wr_widget')
  const ELEMENTS_WR_TYPES_SELECT = document.getElementById('elements_wr_types_select')
  const ELEMENTS_WR_WORKER_RUNS_SELECT = document.getElementById('elements_wr_worker_runs_select')
  const ELEMENTS_WR_SAVE_BUTTON = document.getElementById('elements_wr_worker_save_button')
  const ELEMENTS_WR_INPUT = document.getElementById('id_elements_worker_run')

  /*
   * If there isn't any type or worker run to be selected then the filter
   * is disabled and we don't need to initialize the custom widget
   */
  if (ELEMENTS_WR_INPUT.hasAttribute('disabled')) {
    ELEMENTS_WR_INPUT.setAttribute('placeholder', '')
    return
  }

  // Insert the custom widget at the right place in the form
  const controlDiv = document.getElementById('id_elements_worker_run').parentElement
  const fieldDiv = controlDiv.parentElement
  fieldDiv.insertBefore(ELEMENTS_WR_WIDGET, controlDiv)
  ELEMENTS_WR_WIDGET.classList.remove('is-hidden')

  const typesInput = initCustomSelect(ELEMENTS_WR_TYPES_SELECT)
  const workerRunsInput = initCustomSelect(ELEMENTS_WR_WORKER_RUNS_SELECT)
  // The "Save" button should only be clickable when both selects hold a selected value
  for (const select of [ELEMENTS_WR_TYPES_SELECT, ELEMENTS_WR_WORKER_RUNS_SELECT]) {
    select.addEventListener('change', () => {
      if (typesInput.items.length && workerRunsInput.items.length) ELEMENTS_WR_SAVE_BUTTON.removeAttribute('disabled')
      else ELEMENTS_WR_SAVE_BUTTON.setAttribute('disabled', 'true')
    })
  }

  // The input bound to the form is also initialized with BulmaTagsInput
  ELEMENTS_WR_INPUT.setAttribute('data-type', 'tags')
  ELEMENTS_WR_INPUT.setAttribute('data-selectable', 'false')
  const endInput = new BulmaTagsInput(ELEMENTS_WR_INPUT)

  // Clicking on the "Save" button will populate the bound input with selected values
  ELEMENTS_WR_SAVE_BUTTON.addEventListener('click', () => {
    const [selectedType] = typesInput.items
    const [selectedWorkerRun] = workerRunsInput.items

    // A type can only be associated to one worker run at most, we need to clean any existing association
    const alreadyFilteredType = endInput.items.find((tag) => tag.startsWith(selectedType.value + '='))
    if (alreadyFilteredType) endInput.remove(alreadyFilteredType)

    endInput.add(selectedType.value + '=' + selectedWorkerRun.value)
  })
}

const initMetadataWidget = () => {
  const METADATA_INPUT = document.getElementById('id_metadata')
  METADATA_INPUT.classList.add('ignore-confirm')

  // We are using BulmaTagsInput library for this widget, documentation is available here: https://bulma-tagsinput.netlify.app/get-started/usage/
  METADATA_INPUT.setAttribute('data-type', 'tags')
  METADATA_INPUT.setAttribute('data-selectable', 'false')
  BulmaTagsInput.attach(METADATA_INPUT)
}

const initDatasetSetsWidget = () => {
  const DATASET_SETS = document.getElementById('id_dataset_sets')
  // Add ignore-confirm class so that hitting the enter key doesn't submit the form
  DATASET_SETS.classList.add('ignore-confirm')

  // We are using BulmaTagsInput library for this widget, documentation is available here: https://bulma-tagsinput.netlify.app/get-started/usage/
  DATASET_SETS.setAttribute('data-type', 'tags')
  DATASET_SETS.setAttribute('data-selectable', 'false')
  BulmaTagsInput.attach(DATASET_SETS)
}

const initDatasetOrElement = (orSpanContent) => {
  const DATASET_FIELD = document.getElementById('id_dataset').closest('div.field')
  const DATASET_SETS_FIELD = document.getElementById('id_dataset_sets').closest('div.field')
  const ELEMENT_FIELD = document.getElementById('id_element').closest('div.field')
  const PROCESS_FIELD = document.getElementById('id_name').closest('div.field')

  organizeLeftOrRightFields([ELEMENT_FIELD], [DATASET_FIELD, DATASET_SETS_FIELD], orSpanContent, PROCESS_FIELD)
}

export const bootArkindexImportForm = (confirmContent, orSpanContent) => {
  const form = document.getElementById('arkindex-import-form')
  confirmEnterKeySubmit(form, confirmContent)

  initSortableWidget('transcriptions')

  initSortableWidget('entities')
  updateEntityCheckboxes()
  // Enable/Disable entity checkboxes according to the transcription checkboxes
  const CHECKBOXES = document.querySelectorAll('label.radio input[type=checkbox][name=transcriptions]')
  CHECKBOXES.forEach(checkbox => {
    checkbox.addEventListener('change', updateEntityCheckboxes)
  })

  initDatasetOrElement(orSpanContent)
  initDatasetSetsWidget()
  initElementsWorkerRunWidget()
  initMetadataWidget()
}
