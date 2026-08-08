// Format money: 1234.5 → $1,234.50 

  const fmt = (n) 

        "$" + Number(n || 0)

             .toFixed(2)

              .replace(/\B(?=(\d{3})+(?!\d))/g, ",");



 //2.)(explanation)   using "fmt" helps format a number into currency. const fmt =     (n) =>  // using "fmt" helps format a number into currency. 

        "$" + Number(n || 0)

        // (n || 0) = using falsy, it will define to zero, which will ensure that the function has valid number. 

        //  .toFixed \\ toFixed, it will round up to  2 decmial places 

        //  .replace(/\B(?=(\d{3})+(?!\d))/g, ",");


//I used /\B  to match a position that is not a own  boundary. 

        //(?=(\d{3})+(?!\d)) This is known as "lookahead assertaion " it provides me deatils  if there are three  digits following the zero & also provides me if or not there 

       // are  another digit for ?!\d))

        // g flag it will match the same strings are replaced with commas 

        // "," match postion 

        //Finally this equation  works and solves the equation which will turn out as 1234.5 into $1234.5. 

// Demo data 
       const demo = {
         cash: 12500.75,
         holdings: [
           { ticker: "AAPL", qty: 12, price: 191.12 },
           { ticker: "MSFT", qty: 8, price: 414.22 },
           { ticker: "AMZN", qty: 3, price: 176.45 },
         ],
       };
 
 
       //I used "Demo data" because I am providing a example of how data used as a tester.  
       //I used const demo because it is  the main  languages tool for Java.
      // The objects I used are Apple(AAPL), Microsoft MSFT, and 3 Amazon shares. 
       //This is a example of what it looks like, but after loading the code, it runs to the next step. 
 
 
  ],
 
 };
: 
       // Run when page loads
       document.addEventListener("DOMContentLoaded", async () => {
         const cashEl = document.getElementById("cash-value");
         const portEl = document.getElementById("portfolio-value");
         const tbody = document.querySelector(".data-table tbody");
 
         tbody.innerHTML =
           '<tr><td colspan="4" style="text-align:center;padding:1rem;color:#64748b;">LoadingÉ</td></tr>';

         let cash = demo.cash;
         let holdings = demo.holdings.map((h) => ({ ...h }));
 
         //After it loaded, I use "addEventListener()" because it attaches an event handler. 
        // Next  I put in "DOMContentLoaded", async () => This code runs once the basic HTML document has been completely loaded, which
         //will show results. 
 
         //Based on these three steps, 
         //each has there own java tools that supports these. 
         //cash-value, protfolio , and the  data-table tbody does Element selection
        // let holdings = demo.holdings.map((h) => ({ ...h })) which mean to  avoid modifying the original demo data. 

// Only try backend if URL is set
      if (API_URL) { //empty strings
          try { // supports potential erros
            const [acct, holds, prices] // suports function to make HTTP specific endpoints appended to API_URL
            await Promise.all([ // It takes array of promises and returns a signle promis that resolves when all input promises have resolved
              fetch(API_URL + "/account").then((r) => (r.ok ? r.json() : null)), // fetch(API_URL+) it helps to web API for network requests. It communicateds request to the URLs. 
              fetch(API_URL + "/portfolio/holdings").then((r) =>  // Check if the request was successful
                r.ok ? r.json() : null // "r" holds response object after making an HTTP request. "ok"=will indecate if "true" will work or "false" has errors. "json= r.ok=TRUE"
              ), // I used r.ok because it request as a success
              fetch(API_URL + "/market/tickers").then((r) => // This initiates network request to the specified URL to retrieve data, presumably a list of market tickers and their current prices. 
                r.ok ? r.json() : null
              ), // This is a promise handler that process the servers initial response
            ]);

            if (acct && holds && prices) {
              cash = acct.cash_balance || demo.cash; // cash=account.cash balance \\ demo cash; This line sets the cash variable. It use the cash balances from the account data.
              const priceMap = new Map(
                prices.map((p) => [p.ticker.toUpperCase(), p.current_price])// Creates Map to effeciient lookups of stock prices.  " price array" converts ticker to upper case and mapping.
              );
              holdings = holds.map((h) => ({ // This array by transoforming the orginal holds data
                ticker: h.ticker, // symbol of stock 
                qty: h.quantity, // quantity held
                price: priceMap.get(h.ticker.toUpperCase()) || 0, // attempt to retrieve a value ( presumably a number representing a price) from map using upper version of ticker symbol as the key
              }));
            }
          } catch (e) { //  catch block used for error handling. for example if an error associated try to block, the exection jumps catch the block 
            console.log("Backend not ready –   cusing demo data");// (console.log) data to develope consule. //backed not red) it messages that will be printed to consule.
          }
        }

Part 6
//Calculate total
       const total = holdings.reduce((sum, h) => sum + h.qty * h.price, 0);
        
       
       cashEl.textContent = fmt(cash);
        portEl.textContent = fmt(total);

        Finially, I will be calculating the total. 


         I used "const total" because it code
          the calculation of the total value of portolio. 
          Using the code "holding", this represents the investment holding with properties. 
          As for using the code "reduce" it represents how each elements of the array  applies 
          Using (sum,h)  => sum + h.qty * h.price, 0); The sum accumulates track of the running total, 
          for h, it shows the current element in holding the array, lastly for  h.qty * h.price, it calculates the 
          total value of the current holding which is ( quaitity multiplied by price) 

          cashEl= helps reference to a DOM element where the user cash balances out 
          fmt= Formats the cash value, which means total amount of cash. 



//Part 7 

// Build table
        tbody.innerHTML = "";
        if (holdings.length === 0) {
          tbody.innerHTML =
            '<tr><td colspan="4" style="text-align:center;padding:1.25rem;color:#64748b;">No stocks yet. Buy some!</td></tr>';
        } else {
          holdings.forEach((h) => {
            tbody.insertAdjacentHTML(
              "beforeend",
              `
              <tr>
                <td>${h.ticker}</td>
                <td>${h.qty}</td>
                <td>${fmt(h.price)}</td>
                <td>${fmt(h.qty * h.price)}</td>
              </tr>
            `
            );
          });
        }
      });
    </script>
  </body>
</html>


//<tbody> is purpose of use= to include coding in Java.  






//Lastly, I use the code the tbody.innerHTML=""; 
//This ensures the table has no stocks in it yet. Once added stocks, it will be filled. So the code for (Holding.legth == 0)
//keeps it empty.

//tbody= when using tbody in JavaScripts property set from HTML, it
//shows as tag of table/ rows or cells. 

// When applying '<tr><td colspan="4" style="text-align:center;padding:1.25rem;color:#64748b;">No stocks yet. Buy some!</td></tr>';
 //       } else { this add extra columns
            
// This code "insertAdjacentHTML" is used for beforeend. 

// This row shows ticker, quantity, price and total values.
// <td>${h.ticker}</td> // The stock ticker
//                <td>${h.qty}</td> The quantity of stocks
//                <td>${fmt(h.price)}</td> The formatted price of the stock
//                <td>${fmt(h.qty * h.price)}</td> The formatted total value of the stocks
//              </tr>
        
//script = which is the closing tag element of <HTML>
//</HTML>
//<body> = element contains all the visible content of webpage 
//<html> wraps all the conetent of the webpage inlcued.