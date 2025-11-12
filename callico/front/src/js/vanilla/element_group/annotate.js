import { isEmpty, isEqual, xorWith } from 'lodash'
import { initFormset } from '../utils/formset.js'
import { dispatchUpdateGroups, UPDATE_GROUP_EVENT, DELETE_GROUP_EVENT } from '../events/element_group_manager.js'
import { getUserTaskAnnotation, setUserTaskAnnotation, displayWarning } from '../annotations/storage.js'

const initLibraryEvents = (userTaskID, parentID, groups) => {
  document.addEventListener(UPDATE_GROUP_EVENT, (evt) => {
    const { id, elements } = evt.detail
    groups[id - 1] = { elements }
    setUserTaskAnnotation(userTaskID, parentID, groups)
  })

  document.addEventListener(DELETE_GROUP_EVENT, (evt) => {
    // Only nullify the object to keep the synchronization between ID and list index
    groups[evt.detail - 1] = null
    setUserTaskAnnotation(userTaskID, parentID, groups)
  })
}

export const bootElementGroupAnnotate = (userTaskID, parentID, previousGroups) => {
  const groups = getUserTaskAnnotation(userTaskID, parentID) || previousGroups
  if (!isEmpty(xorWith(groups.filter(group => group), previousGroups, isEqual))) displayWarning(userTaskID, parentID)
  dispatchUpdateGroups(groups)

  initFormset(groups, (key, value) => value)
  initLibraryEvents(userTaskID, parentID, groups)
}
