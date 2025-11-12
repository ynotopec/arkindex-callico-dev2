import axios from 'axios'
import { API_BASE_URL } from './config'

if (!API_BASE_URL) throw new Error('Missing API_BASE_URL')
axios.defaults.baseURL = API_BASE_URL

// Retrieve an element.
export const retrieveElement = async id => (await axios.get(`/element/${id}/`)).data

// List values from an authority.
export const listAuthorityValues = async (id, search) => (await axios.get(`/authority/${id}/values/`, { params: { search } })).data
