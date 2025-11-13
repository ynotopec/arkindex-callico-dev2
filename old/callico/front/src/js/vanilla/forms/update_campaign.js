// eslint-disable-next-line import/no-named-as-default
import Sortable from 'sortablejs'

import { initDynamicFormset } from '../utils/formset.js'

const UPDATE_CAMPAIGN_FORM_ID = 'update-campaign-form'
const EF_FIELD_ROW_CLASS = 'field-row'
const EF_GROUP_ROW_CLASS = 'group-row'
const EF_FIELD_TYPE_CLASS_ATTR = 'field-type'
const EF_GROUP_LEGEND_CLASS_ATTR = 'group-legend'
const EF_FIELD_LABEL_CLASS = 'field-label'
const EF_ORDER_INPUT_ID = 'id_entities_order'
const ROOT_GROUP = '-1'

const canMoveInGroup = (evt) => {
  /*
   * Assert that whenever we move a field from a group, it is not appended to the
   * root (before the group name row).
   *
   * If the destination group is not the root:
   *   - return `true` to keep default insertion point based on the direction
   * Else:
   *   - return `false` to cancel the move
   *
   * See https://github.com/SortableJS/Sortable/blob/master/README.md?plain=1#L211
   * for more details on the return value.
   */
  const toGroup = evt.related.getAttribute('group-idx')
  return toGroup !== ROOT_GROUP
}

const updateEntityFormOrderInput = () => {
  const orderInput = document.getElementById(EF_ORDER_INPUT_ID)
  if (!orderInput) return

  const newOrder = []
  document.querySelectorAll(`tr.${EF_FIELD_ROW_CLASS}, tr.${EF_GROUP_ROW_CLASS}`).forEach((row) => {
    if (row.classList.contains(EF_GROUP_ROW_CLASS)) {
      const groupLegend = row.querySelector(`td.${EF_GROUP_LEGEND_CLASS_ATTR}`).getAttribute(EF_GROUP_LEGEND_CLASS_ATTR)
      newOrder.push([groupLegend, '', ''])
      return
    }

    const group = row.getAttribute('group')
    const fieldType = row.querySelector(`td.${EF_FIELD_TYPE_CLASS_ATTR}`).getAttribute(EF_FIELD_TYPE_CLASS_ATTR)
    const fieldLabel = row.querySelector(`td.${EF_FIELD_LABEL_CLASS}`).textContent.trim()
    newOrder.push([group, fieldType, fieldLabel])
  })

  orderInput.setAttribute('value', JSON.stringify(newOrder))
}

const initEntityFormSortableObjects = () => {
  const rows = document.querySelectorAll(`tr.${EF_FIELD_ROW_CLASS}, tr.${EF_GROUP_ROW_CLASS}`)
  if (!rows) return

  // Listing all available groups
  const groups = new Set(Array.from(rows).map(row => row.getAttribute('group-idx')))

  // Creating one Sortable component for each group (root included)
  groups.forEach(group => {
    // One line from this specific group
    const row = document.querySelector(`tr[group-idx="${group}"].${EF_FIELD_ROW_CLASS}, tr[group-idx="${group}"].${EF_GROUP_ROW_CLASS}`)

    // Define to which parent the Sortable component refer to and add options when needed
    const [parent, keyword, extraOption] = group === ROOT_GROUP ? [row.parentElement.parentElement, 'root', {}] : [row.parentElement, group, { onMove: (evt) => canMoveInGroup(evt) }]

    // Instantiate Sortable on "is-grabbable-{group}" buttons for this group
    Sortable.create(parent, {
      group,
      handle: `.is-grabbable-${keyword}`,
      animation: 150,
      // When anything moves, we update the whole order to avoid dumb mistakes
      onEnd: () => updateEntityFormOrderInput(),
      ...extraOption
    })
  })
}

export const bootUpdateCampaignForm = (campaignMode) => {
  if (campaignMode === 'entity form') {
    initEntityFormSortableObjects()
  } else {
    initDynamicFormset()
  }

  // Truncate really long options
  document.querySelectorAll(`#${UPDATE_CAMPAIGN_FORM_ID} label.radio`).forEach(option => {
    option.classList.add('truncate-long-words')
    option.setAttribute('title', option.textContent)
  })
}
