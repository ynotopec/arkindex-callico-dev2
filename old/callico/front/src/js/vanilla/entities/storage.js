import { getUserTaskAnnotation } from '../annotations/storage.js'
import { DEFAULT_ENTITY_COLOR, getColor } from './labels.js'

export const loadStoredEntities = (userTaskID, parentID, transcription) => {
  if (!transcription) return null

  const entities = getUserTaskAnnotation(userTaskID, parentID) || []

  for (const entity of [...entities]) {
    /*
     * Remove invalid entities to avoid form errors
     * This can happen if the configuration has changed
     */
    const color = getColor(entity.entity_type)
    if (color === DEFAULT_ENTITY_COLOR) {
      entities.splice(entities.indexOf(entity), 1)
      continue
    }

    /*
     * Remove invalid entities to avoid form errors
     * This can happen if the transcription has changed
     */
    if (entity.offset + entity.length > transcription.length) {
      entities.splice(entities.indexOf(entity), 1)
      continue
    }
  }

  return entities.length ? entities : null
}
