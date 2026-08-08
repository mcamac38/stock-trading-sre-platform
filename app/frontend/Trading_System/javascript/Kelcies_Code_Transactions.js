// part 1 Set the API URL - this is where we get transaction data from
      window.API_BASE_URL = window.API_BAE_URL ||
        "https://6hhdszthdg.execute-api.us-east-1.amazonaws.com/prod";

        //I used window.API_BASE_URL which attached to the browser's window object (making it a global variable, accessible by all other scripts on the page)
        //As for  "https://6hhdszthdg.execute-api.us-east-1.amazonaws.com/prod"; This is the default CSSMathValue, a specific URL String, representing the base address for an API that provides transaction data 


 // part 2 Helper function: format numbers as money (adds $ and commas)
      function fmtMoney(n) {
        return Number(n || 0).toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        });
      
      }

      //I will explain and what these do, function fmtMoney(N) Defines a function named fmtMoney that accepts one argument n. 
      //As for Number(n\\0) it helps to operate to check if "n" has a "truthy"value or n is"falsy" 
    // The Number (n || 0) converts the result value into a number 
    // .toLocaleString(undefined, {...})  It converts the number to a string using language senstive representation.
    //undefined current locale
    //  minimumFractionDigits: Ensures the at lest two digits appear after the decimal points 

//part 3

       // Helper function: fetch data from a URL and return as JSON
      async function fetchJson(url, opts) {
        const res = await fetch(url, opts); // Make the request
        if (!res.ok) throw new Error("HTTP " + res.status); // Check if request failed
        return await res.json(); // Convert response to JavaScript object
      }





//Part 4 Main function: load and display transactions
      async function loadTransactions() {
        const tbody = document.querySelector(".data-table tbody"); 
        // Find the table body where we'll show data
        const typeFilter = document.getElementById("filterType"); // Get the type filter dropdown
        const symbolFilter = document.getElementById("symbolFilter"); // Get the symbol filter input

        // Show "Loading..." message while we fetch data
        if (tbody)
          tbody.innerHTML =
            '<tr><td colspan="6" style="text-align:center; padding:1rem; color:#64748b;">Loading…</td></tr>';

        let transactions = []; // Array to store all transactions

        try {

      //I used the asyn function because it declares a function that can handle asynchronous operations ( it can build a database).
      //The "loadTransactioins" it is to display transaction data 
      //As for the "const tbody" a reference to a specific HTML element that 
      //cannot be reassigned later in the code 
      //"document.querySelector"  supports seraching for the entire HTML that mataches the provided CSS selector. 
      //"data-table tbody" - knowns for CSS selector

      //This code defines a function designed to perform a task like transaction data. 
      //The main purpose of this code is to find the specific part of the HTML
      //table where transaction data rows likely be inserted. 
	   
//Part 5  Try to get real data from the backend API (no authentication needed)
          const data = await fetchJson(
            API_BASE_URL + "/portfolio/transactions",
            {}
          )

            //I used "const data" Declares a constant variable named data to store the result of opreation 
            //"await"= execution of function and for (the fetchJson call) it is used to complete and return a value 
            //As for the API_BASE_URL API_BASE_URL + "/portfolio/transactions", it holds the base address of the API 

//Part 6  Empty options = no auth headers
          transactions = Array.isArray(data) ? data : []; // Make sure we have an array
        } catch (e) {

          //As for the Array.isArray(data): it is to check the value stored in the data variable in java
          //? data- ternary operator 
          // If backend fails, use test data so the page still works
          transactions = [
            {
              created_at: new Date().toISOString(),
              type: "deposit",
              amount: 5000,


              //transation = is assigned the value of data 
              //
            }, // Recent deposit
            {
              created_at: new Date(Date.now() - 3600000).toISOString(),
              type: "buy",
              ticker: "AAPL",
              quantity: 10,
              price: 190.25,
            }, // 1 hour ago
            {
              created_at: new Date(Date.now() - 7200000).toISOString(),
              type: "sell",
              ticker: "MSFT",
              quantity: 4,
              price: 412.1,
                          }, // 2 hours ago
            {
              created_at: new Date(Date.now() - 14400000).toISOString(),
              type: "withdraw",
              amount: 250,
            }, // 4 hours ago
            {
              created_at: new Date(Date.now() - 21600000).toISOString(),
              type: "buy",
              ticker: "AMZN",
              quantity: 3,
              price: 176.45,
            }, // 6 hours ago
          ];
        }


          //For this part to work newDate(Date.now) is a Timestamp which generates a timestamp for one hour before hte code was executed 
          //Date.new = helps return the current time 
         // .toISOString() formats this time into an ISO 8601 string
         // buy= indicates the share were purchaed 
         // ticker = identifies apple
          //quanitity - specifices that 10 were bought 
         // price = indeicate the purchase price per share 


//Part 7. Get filter values from the form
        const typeVal = typeFilter?.value || "all"; // Get selected type (buy, sell, etc.) or 'all'
        const symbolVal = (symbolFilter?.value || "").trim().toUpperCase(); // Get symbol filter and make uppercase


      //I used const typeVal because it stores the results filter value 
     // Then I added typeFilter? this uses optional chaining operator , which it checks if the typerFilter variable is null. or not null  
     // Value - Accesses the value entered

        //|| "all": This uses the logical 
       // One thing i learned from this is that typeFilter?.value is a falsy value which expresses "all"
       // which is part of the typeFilter = missing/empty "all"
       //const symbolVal - it helps store the resulting symbol value 
       //symbolFilter?.value = supports to attempt safety to get the values
       //trim()= removes leading and trailing whitespace. 

//Part 8 Filter transactions based on user's selections
        let filtered = transactions.filter((t) => {
          const tType = String(t.type || t.side || "").toLowerCase(); // Get transaction type
          const tSymbol = String(t.ticker || t.symbol || "").toUpperCase(); // Get stock symbol
          const typeMatch =
            typeVal === "all" || tType === typeVal.toLowerCase(); // Check if type matches
          const symbolMatch = !symbolVal || tSymbol.includes(symbolVal); // Check if symbol matches
          return typeMatch && symbolMatch; // Keep transaction if both filters pass
        });
	   