// eslint-disable-next-line import/no-named-as-default
import Sortable from 'sortablejs'

import { confirmEnterKeySubmit } from '../utils/enter_key_submit.js'

const initSortableEntitiesWidget = (form) => {
  const checkboxes = document.querySelectorAll('[id^=id_entities_order_]')
  if (!checkboxes.length) return

  checkboxes.forEach(checkbox => {
    // Hide and disable the checkbox button
    checkbox.setAttribute('hidden', '')
    checkbox.addEventListener('click', (evt) => evt.preventDefault())

    // Display the grabbable icon instead
    const i = document.createElement('i')
    i.classList.add('fas', 'fa-grip-vertical')

    const span = document.createElement('span')
    span.classList.add('icon', 'is-grabbable')
    span.appendChild(i)

    checkbox.parentElement.insertBefore(span, checkbox)
  })

  // We have at least one configured entity
  Sortable.create(checkboxes[0].parentElement.parentElement, {
    handle: '.is-grabbable',
    animation: 150
  })
}

export const bootArkindexExportForm = (confirmContent) => {
  const form = document.getElementById('arkindex-export-form')
  confirmEnterKeySubmit(form, confirmContent)

  initSortableEntitiesWidget(form)
}
