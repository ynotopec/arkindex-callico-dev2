// Build an object from all <meta> tags
const metas = [...document.getElementsByTagName('meta')].reduce((obj, meta) => { obj[meta.name] = meta.content; return obj }, {})

// Support fully specified URL with scheme, but also relative URLs to this page (like /api/v1)
export const API_BASE_URL = new URL(metas.api_base_url || '', window.location.href).href

// Image definition related to available space
export const IMAGE_QUALITY = 4

// Image zoom factor in percent
export const ZOOM_FACTORS = [100, 133, 166, 200, 250, 350, 400, 500]

// Image navigation transitions delay for the zoom and the automatic centering (ms)
export const IMAGE_TRANSITIONS = 300

// Margins allowed navigating through an image in percentage of the image max(width, height)
export const NAVIGATION_MARGINS = 5

// Display a warning message once the ratio between the expected and actual image dimensions or area exceeds 80% or 120%
export const IMAGE_WARNING_RATIO = 0.8

// Polygon drawing colors
export const INTERACTIVE_POLYGON_COLORS = {
  visible: '#28b62c',
  selected: 'cornflowerblue',
  highlighted: 'yellow'
}

// Polygon minimal height and width (in pixels relatively to the image dimensions)
export const POLYGON_MIN_SIZE = 2

/*
 * Maximum allowed consecutive distinct points in a polygon in the backend:
 * AAABBBCCCBBBCCCCDDD has 6 distinct points even though B and C are repeated,
 * but ABCDA has 4 distinct points because the last point is ignored when it is equal to the first.
 */
export const POLYGON_MAX_POINTS = 163

// Interaction modes
export const DISPLAY_MODE = 'display'
export const SELECT_MODE = 'select'
export const CREATE_MODE = 'create'

export const ELEMENT_MODES = [DISPLAY_MODE, SELECT_MODE, CREATE_MODE]

// Drawing tools
export const RECTANGLE_TOOL = 'rectangle'
export const POLYGON_TOOL = 'polygon'
export const EDITION_TOOL = 'edit'

const LANGUAGE = document.documentElement.lang
const ALL_TRANSLATIONS = {
  en: {
    imageError: (imageURL) => `An error occurred while loading this image from the IIIF server at ${imageURL}.`,
    imageSizeError: (actualSize, expectedSize, imageURL) => `The size of the provided image is ${actualSize}, but ${expectedSize} was expected. There may be an issue with the IIIF server at ${imageURL}.`,
    elementError: 'Retrieving the element failed.',
    element: 'element',
    colon: ':',
    create: (groupType) => `create new "${groupType}" group`,
    delete: (groupType) => `delete this "${groupType}" group`,
    empty: 'is empty',
    in: 'in'
  },
  fr: {
    imageError: (imageURL) => `Une erreur est survenue lors du chargement de cette image depuis le serveur IIIF à l'adresse ${imageURL}.`,
    imageSizeError: (actualSize, expectedSize, imageURL) => `La taille de l'image fournie est ${actualSize}, mais ${expectedSize} était attendu. Il se pourrait qu'il y ait un problème avec le serveur IIIF à l'adresse ${imageURL}.`,
    elementError: 'La récupération de l\'élément a échouée.',
    element: 'élément',
    colon: ' :',
    create: (groupType) => `créer un nouveau groupe "${groupType}"`,
    delete: (groupType) => `supprimer ce groupe "${groupType}"`,
    empty: 'est vide',
    in: 'dans'
  }
}

export const TRANSLATIONS = ALL_TRANSLATIONS[LANGUAGE]
