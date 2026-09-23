To run a React JS app, here are the most common methods:
Method 1: Using npm (Most Common)
bash

# Install dependencies (first time only)
npm install

# Start the development server
npm start

The app will open at http://localhost:3000 by default.
Method 2: Using yarn
bash

# Install dependencies (first time only)
yarn install

# Start the development server
yarn start

Method 3: Using npx
bash

# If you have a create-react-app project
npx react-scripts start

Check Your package.json

Look at your package.json file to see what scripts are available:
json

"scripts": {
  "start": "react-scripts start",  // Development
  "build": "react-scripts build",  // Production build
  "test": "react-scripts test",    // Run tests
  "eject": "react-scripts eject"   // Eject from CRA
}

Other Common Scenarios
Vite-based React App
bash

npm run dev
# or
yarn dev

Next.js React App
bash

npm run dev
# or
yarn dev

If using a specific port
bash

# Change port to 4000
PORT=4000 npm start

# Or on Windows
set PORT=4000 && npm start

Troubleshooting

If you get errors:

    "Command not found" → Make sure Node.js is installed (node -v)

    "Module not found" → Run npm install again

    Port already in use → Use a different port (e.g., PORT=3001 npm start)

Production Build
bash

# Create optimized production build
npm run build

# Serve it locally (install serve first)
npx serve -s build