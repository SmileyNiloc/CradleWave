// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyAVmVZPCvdiUzyHPVj-QC6l66qJaHAMQGg",
  authDomain: "cradlewave-aa74f.firebaseapp.com",
  databaseURL: "https://cradlewave-aa74f-default-rtdb.firebaseio.com",
  projectId: "cradlewave-aa74f",
  storageBucket: "cradlewave-aa74f.firebasestorage.app",
  messagingSenderId: "351958736605",
  appId: "1:351958736605:web:68fddf48fec7016654c534",
  measurementId: "G-YWFVYM8NHD",
};

// Initialize Firebase
export const firebaseApp = initializeApp(firebaseConfig);

const db = getFirestore(firebaseApp);

export { db };
